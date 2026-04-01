"""Stress-test for the Load More button recovery logic.

Clicks "Load More" many times against a live CryptoPanic page (via Chrome
on port 9222) and records every button-state transition, timing, and
failure.  The goal is to observe how often the button gets stuck and
whether the current recovery logic reliably continues.

Prerequisites:
    google-chrome --remote-debugging-port=9222 \
        --user-data-dir=/tmp/cryptopanic-debug-profile \
        'https://www.cryptopanic.com/news'

Run:
    python -m pytest tests/test_load_more_stress.py -v -s
"""

import json
import time

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException

from cryptopanic_scraper import config

DEBUGGER_ADDRESS = "127.0.0.1:9222"
PAGE_LOAD_TIMEOUT = 15
# Number of Load More clicks to attempt in the stress test
STRESS_CLICKS = 30


@pytest.fixture(scope="module")
def driver():
    """Attach to Chrome on port 9222."""
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", DEBUGGER_ADDRESS)
    try:
        drv = webdriver.Chrome(options=options)
    except Exception as e:
        pytest.skip(
            f"Cannot attach to Chrome at {DEBUGGER_ADDRESS}. "
            f"Launch Chrome with --remote-debugging-port=9222 first. Error: {e}"
        )
    yield drv


def _get_feed_state(driver) -> dict:
    """Mirror the scraper's _get_feed_state so we can compare."""
    rows = driver.find_elements(By.CSS_SELECTOR, config.SELECTORS["news_row"])
    state = {"count": len(rows), "last_date": "", "last_href": ""}
    if not rows:
        return state
    last_row = rows[-1]
    try:
        time_el = last_row.find_element(By.CSS_SELECTOR, "time")
        state["last_date"] = time_el.get_attribute("datetime") or ""
    except Exception:
        pass
    try:
        link_el = last_row.find_element(By.CSS_SELECTOR, "a.news-cell.nc-title")
        state["last_href"] = link_el.get_attribute("href") or ""
    except Exception:
        pass
    return state


def _get_button_state(driver) -> dict:
    """Mirror the scraper's _get_load_more_button_state."""
    return driver.execute_script("""
        const btn = document.querySelector('button.btn-outline-primary');
        if (!btn) {
            return {
                present: false, text: '', disabled: false,
                aria_disabled: false, class_name: '', has_spinner: false,
                outer_html: ''
            };
        }
        return {
            present: true,
            text: (btn.innerText || btn.textContent || '').trim(),
            disabled: !!btn.disabled,
            aria_disabled: (btn.getAttribute('aria-disabled') || '').toLowerCase() === 'true',
            class_name: btn.className || '',
            has_spinner: !!btn.querySelector(
                '.spinner-border, .spinner-grow, .spinner, [class*="spinner"]'),
            outer_html: btn.outerHTML.substring(0, 300)
        };
    """)


def _click_and_observe(driver, click_num, log):
    """Click Load More once and record what happens, returning (success, entry)."""
    entry = {"click": click_num, "t_start": time.time()}

    # --- Capture before state ---
    before = _get_feed_state(driver)
    btn_before = _get_button_state(driver)
    entry["before_count"] = before["count"]
    entry["btn_before"] = btn_before

    if not btn_before["present"]:
        entry["outcome"] = "NO_BUTTON"
        entry["t_elapsed"] = 0
        log.append(entry)
        return False, entry

    # --- Click the button ---
    try:
        btn_el = driver.find_element(By.CSS_SELECTOR, "button.btn-outline-primary")
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();",
            btn_el,
        )
    except WebDriverException as e:
        entry["outcome"] = f"CLICK_FAILED: {e}"
        entry["t_elapsed"] = time.time() - entry["t_start"]
        log.append(entry)
        return False, entry

    # --- Poll for progress (matching the scraper's logic) ---
    time.sleep(config.SCROLL_PAUSE)
    poll_deadline = time.time() + PAGE_LOAD_TIMEOUT
    progressed = False

    while time.time() < poll_deadline:
        try:
            after = _get_feed_state(driver)
        except WebDriverException:
            time.sleep(config.LOAD_MORE_POLL_INTERVAL)
            continue
        if (after["count"] > before["count"]
                or after["last_date"] != before["last_date"]
                or after["last_href"] != before["last_href"]):
            progressed = True
            entry["after_count"] = after["count"]
            entry["new_rows"] = after["count"] - before["count"]
            break
        time.sleep(config.LOAD_MORE_POLL_INTERVAL)

    btn_after = _get_button_state(driver)
    entry["btn_after"] = btn_after
    entry["t_elapsed"] = time.time() - entry["t_start"]

    if progressed:
        entry["outcome"] = "OK"
        log.append(entry)
        return True, entry

    # --- No progress: check if stuck spinner ---
    is_stuck = (
        btn_after["present"]
        and (btn_after["disabled"] or btn_after["aria_disabled"])
        and (
            "loading" in btn_after["text"].lower()
            or "spinner" in btn_after["class_name"].lower()
            or btn_after["has_spinner"]
        )
    )
    entry["stuck_spinner_detected"] = is_stuck

    if is_stuck:
        # Try the scraper's revive logic
        entry["revive_attempted"] = True
        driver.execute_script("""
            const btn = document.querySelector('button.btn-outline-primary');
            if (!btn) return false;
            btn.scrollIntoView({block: 'center'});
            btn.disabled = false;
            btn.removeAttribute('disabled');
            btn.setAttribute('aria-disabled', 'false');
            ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(type => {
                btn.dispatchEvent(new MouseEvent(type, {
                    bubbles: true, cancelable: true, view: window}));
            });
            return true;
        """)
        time.sleep(config.SCROLL_PAUSE)

        # Wait another grace period for feed progress
        grace_deadline = time.time() + config.LOAD_MORE_GRACE_TIMEOUT
        while time.time() < grace_deadline:
            try:
                after = _get_feed_state(driver)
            except WebDriverException:
                time.sleep(config.LOAD_MORE_POLL_INTERVAL)
                continue
            if (after["count"] > before["count"]
                    or after["last_date"] != before["last_date"]
                    or after["last_href"] != before["last_href"]):
                progressed = True
                entry["after_count"] = after["count"]
                entry["new_rows"] = after["count"] - before["count"]
                break
            time.sleep(config.LOAD_MORE_POLL_INTERVAL)

        entry["revive_success"] = progressed
        entry["t_elapsed"] = time.time() - entry["t_start"]

        btn_after_revive = _get_button_state(driver)
        entry["btn_after_revive"] = btn_after_revive

        if progressed:
            entry["outcome"] = "REVIVE_OK"
        else:
            entry["outcome"] = "STUCK_UNRECOVERABLE"
    else:
        entry["outcome"] = "TIMEOUT_NO_SPINNER"

    log.append(entry)
    return progressed, entry


def test_load_more_stress(driver):
    """Click Load More STRESS_CLICKS times, recording every outcome.

    This test always passes — it's a diagnostic that prints a detailed
    report of how reliable Load More is and where it gets stuck.
    """
    # Navigate to a fresh feed — retry up to 3 times for 502 / Cloudflare
    feed_loaded = False
    for attempt in range(3):
        driver.get(f"{config.BASE_URL}?filter=all")
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, config.SELECTORS["news_row"])
                )
            )
            feed_loaded = True
            break
        except TimeoutException:
            title = driver.title or ""
            print(f"  Attempt {attempt+1}: page did not load ({title}), retrying...")
            time.sleep(5)

    if not feed_loaded:
        pytest.skip("Could not load CryptoPanic feed after 3 attempts (502/Cloudflare)")

    # Remove blur overlay
    driver.execute_script(
        'document.querySelectorAll(".blur-overlay").forEach(e => e.remove());'
    )
    time.sleep(1)

    log = []
    consecutive_failures = 0
    max_consecutive_failures = 0

    print(f"\n{'='*70}")
    print(f"  LOAD MORE STRESS TEST — {STRESS_CLICKS} clicks")
    print(f"{'='*70}")

    for i in range(1, STRESS_CLICKS + 1):
        success, entry = _click_and_observe(driver, i, log)

        symbol = "✓" if success else "✗"
        outcome = entry["outcome"]
        elapsed = entry["t_elapsed"]
        before_c = entry.get("before_count", "?")
        after_c = entry.get("after_count", "?")
        new_r = entry.get("new_rows", 0)

        print(f"  [{symbol}] Click {i:3d}: {outcome:<25s} "
              f"rows {before_c} -> {after_c} (+{new_r})  "
              f"[{elapsed:.1f}s]")

        if not success:
            consecutive_failures += 1
            max_consecutive_failures = max(max_consecutive_failures, consecutive_failures)

            if entry.get("stuck_spinner_detected"):
                print(f"        Button state: text={entry['btn_after']['text']!r} "
                      f"disabled={entry['btn_after']['disabled']} "
                      f"spinner={entry['btn_after']['has_spinner']}")
                if entry.get("btn_after_revive"):
                    print(f"        After revive: text={entry['btn_after_revive']['text']!r} "
                          f"disabled={entry['btn_after_revive']['disabled']} "
                          f"spinner={entry['btn_after_revive']['has_spinner']}")

            # If button disappeared, stop
            if outcome == "NO_BUTTON":
                print("        Button disappeared from DOM — stopping.")
                break
        else:
            consecutive_failures = 0

    # --- Summary ---
    total = len(log)
    ok = sum(1 for e in log if e["outcome"] == "OK")
    revived = sum(1 for e in log if e["outcome"] == "REVIVE_OK")
    stuck = sum(1 for e in log if e["outcome"] == "STUCK_UNRECOVERABLE")
    timeout_no_spin = sum(1 for e in log if e["outcome"] == "TIMEOUT_NO_SPINNER")
    click_fail = sum(1 for e in log if e["outcome"].startswith("CLICK_FAILED"))
    no_button = sum(1 for e in log if e["outcome"] == "NO_BUTTON")
    times = [e["t_elapsed"] for e in log if e["outcome"] in ("OK", "REVIVE_OK")]

    print(f"\n{'='*70}")
    print(f"  RESULTS  ({total} clicks attempted)")
    print(f"{'='*70}")
    print(f"  OK (immediate):          {ok}")
    print(f"  OK (after revive):       {revived}")
    print(f"  STUCK (unrecoverable):   {stuck}")
    print(f"  TIMEOUT (no spinner):    {timeout_no_spin}")
    print(f"  CLICK_FAILED:            {click_fail}")
    print(f"  NO_BUTTON:               {no_button}")
    print(f"  Max consecutive fails:   {max_consecutive_failures}")
    if times:
        print(f"  Avg time (successes):    {sum(times)/len(times):.1f}s")
        print(f"  Max time (successes):    {max(times):.1f}s")
    print(f"{'='*70}")

    # Dump full log for post-mortem
    print("\n  Full log (JSON):")
    # Strip outer_html from log to keep it readable
    clean_log = []
    for e in log:
        ce = dict(e)
        for k in ("btn_before", "btn_after", "btn_after_revive"):
            if k in ce and isinstance(ce[k], dict):
                ce[k] = {kk: vv for kk, vv in ce[k].items() if kk != "outer_html"}
        clean_log.append(ce)
    print(json.dumps(clean_log, indent=2, default=str))

    # This is a diagnostic test — the real assertion is that we gathered data.
    # But we DO assert that the recovery logic at least doesn't crash.
    assert total > 0, "No clicks were attempted"

    # Warn if stuck rate is high
    if stuck > 0:
        print(f"\n  ⚠ WARNING: {stuck} clicks were STUCK and UNRECOVERABLE.")
        print("    The current revive logic did not recover these.")
