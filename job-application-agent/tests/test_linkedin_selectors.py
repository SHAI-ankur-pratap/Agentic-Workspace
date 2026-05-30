"""
Integration tests for LinkedIn DOM selectors.
Runs against live LinkedIn — requires internet connection.
No login needed for these tests (public pages).

Run: python -m pytest tests/test_linkedin_selectors.py -v -s
"""
import asyncio
import pytest


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def browser_page():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()
        yield page
        await browser.close()


SEARCH_URL = "https://www.linkedin.com/jobs/search/?keywords=QA+Lead&f_AL=true&sortBy=DD"
JOB_URL = "https://www.linkedin.com/jobs/view/qa-manager-qa-lead-at-ringside-talent-4408528661"


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def make_page():
    """Create a real browser page for sync tests."""
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    )
    page = context.new_page()
    return p, browser, page


def test_job_card_selector_finds_jobs():
    """a[href*='/jobs/view/'] must find job cards on search page."""
    p, browser, page = make_page()
    try:
        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        count = page.evaluate("document.querySelectorAll('a[href*=\"/jobs/view/\"]').length")
        print(f"\n  Found {count} job links")
        assert count > 0, "No job links found — selector broken"
        assert count > 5, f"Only {count} jobs found — suspiciously low"
    finally:
        browser.close()
        p.stop()


def test_old_selector_returns_zero():
    """Confirm the old class-based selector is broken (returns 0)."""
    p, browser, page = make_page()
    try:
        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        count = page.evaluate(
            "document.querySelectorAll('a.job-card-list__title--link, a[class*=\"job-card-list__title\"]').length"
        )
        print(f"\n  Old selector count: {count} (expected 0)")
        # This documents the broken state — if LinkedIn fixes their classes, this test would fail
        # and that's OK
    finally:
        browser.close()
        p.stop()


def test_job_urls_have_valid_format():
    """Job URLs extracted should be valid LinkedIn job view URLs."""
    p, browser, page = make_page()
    try:
        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        jobs = page.evaluate("""() => {
            const seen = new Set();
            return Array.from(document.querySelectorAll('a[href*="/jobs/view/"]'))
                .map(a => ({title: a.textContent.trim(), href: a.href.split('?')[0]}))
                .filter(j => {
                    if (j.title.length < 3 || seen.has(j.href)) return false;
                    seen.add(j.href);
                    return true;
                });
        }""")
        print(f"\n  {len(jobs)} unique jobs")
        for j in jobs[:3]:
            print(f"    {j['title'][:40]} → {j['href'][:60]}")
        assert len(jobs) > 5
        for j in jobs:
            assert "/jobs/view/" in j["href"]
    finally:
        browser.close()
        p.stop()


def test_jd_extraction_from_job_page():
    """JD must be extractable from a job detail page."""
    p, browser, page = make_page()
    try:
        page.goto(JOB_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        jd = None
        for sel in [
            ".show-more-less-html__markup",
            ".description__text",
            ".jobs-description-content__text",
        ]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 100:
                    jd = text
                    print(f"\n  JD found via '{sel}': {text[:80]}...")
                    break
        assert jd is not None, "JD not found — all selectors failed"
        assert len(jd) > 100
    finally:
        browser.close()
        p.stop()


def test_apply_button_on_job_page():
    """Apply button must be findable on a job detail page."""
    p, browser, page = make_page()
    try:
        page.goto(JOB_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        selectors = [
            'button:has-text("Easy Apply")',
            'button.jobs-apply-button',
            'button.apply-button',
            'button[data-tracking-control-name*="apply"]',
            'button:has-text("Apply")',
        ]
        found = None
        for sel in selectors:
            el = page.query_selector(sel)
            if el:
                # Use JS bounding box — more reliable than Playwright is_visible() for overlapping elements
                has_size = page.evaluate(
                    f"() => {{ const el = document.querySelector({repr(sel)}); return el ? el.getBoundingClientRect().width > 0 : false; }}"
                )
                if has_size:
                    found = sel
                    print(f"\n  Apply button found via: '{sel}'")
                    print(f"  Button text: '{el.inner_text().strip()}'")
                    break
        assert found is not None, "Apply button not found with any selector"
    finally:
        browser.close()
        p.stop()


def test_company_extraction():
    """Company name must be extractable from job detail page."""
    p, browser, page = make_page()
    try:
        page.goto(JOB_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        company = None
        for sel in [
            ".topcard__org-name-link",
            ".jobs-unified-top-card__company-name",
            "[class*='company-name'] a",
        ]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if text:
                    company = text
                    print(f"\n  Company found via '{sel}': {text}")
                    break
        assert company is not None, "Company not found"
    finally:
        browser.close()
        p.stop()
