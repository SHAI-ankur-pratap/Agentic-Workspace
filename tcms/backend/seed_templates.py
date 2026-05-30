"""Seed the 3 built-in test case templates on first startup."""
from database import SessionLocal
from models import Template


REACT_CRUD_CASES = [
    {"title": "Login with valid credentials", "steps": "1. Navigate to /login\n2. Enter valid email and password\n3. Click Sign In", "expected_result": "User is redirected to dashboard", "priority": "P1"},
    {"title": "Login with invalid password", "steps": "1. Navigate to /login\n2. Enter valid email, wrong password\n3. Click Sign In", "expected_result": "Error message 'Invalid credentials' shown, user stays on login", "priority": "P1"},
    {"title": "Login with empty fields", "steps": "1. Navigate to /login\n2. Leave email and password blank\n3. Click Sign In", "expected_result": "Validation errors shown on both fields", "priority": "P2"},
    {"title": "Create new record — happy path", "steps": "1. Navigate to the list view\n2. Click 'Add New'\n3. Fill all required fields\n4. Click Save", "expected_result": "Record appears in list with correct values, success toast shown", "priority": "P1"},
    {"title": "Create record with missing required field", "steps": "1. Click 'Add New'\n2. Leave a required field blank\n3. Click Save", "expected_result": "Inline validation error shown, form not submitted", "priority": "P2"},
    {"title": "Edit existing record", "steps": "1. Click Edit on an existing record\n2. Modify a field value\n3. Click Save", "expected_result": "Record updated in list and detail view", "priority": "P1"},
    {"title": "Delete record with confirmation", "steps": "1. Click Delete on a record\n2. Confirm deletion in dialog", "expected_result": "Record removed from list, success message shown", "priority": "P1"},
    {"title": "Delete record — cancel confirmation", "steps": "1. Click Delete on a record\n2. Click Cancel in dialog", "expected_result": "Record not deleted, list unchanged", "priority": "P2"},
    {"title": "Search/filter list", "steps": "1. Navigate to list view\n2. Enter search term in filter field", "expected_result": "Only matching records shown", "priority": "P2"},
    {"title": "Empty state — no records", "steps": "1. Navigate to list view with no records", "expected_result": "Empty state message shown, not an error or blank page", "priority": "P3"},
    {"title": "Pagination — next page", "steps": "1. Navigate to list with more records than page size\n2. Click Next", "expected_result": "Next page of records shown, pagination updates", "priority": "P2"},
    {"title": "Form field max length validation", "steps": "1. Open create form\n2. Enter text exceeding max length in a text field", "expected_result": "Input capped at max or validation error shown", "priority": "P3"},
    {"title": "Responsive — mobile form layout", "steps": "1. Open create form on 375px viewport", "expected_result": "All fields visible and usable, no horizontal scroll", "priority": "P3"},
    {"title": "Keyboard navigation in form", "steps": "1. Open create form\n2. Navigate fields using Tab key", "expected_result": "Focus moves through fields in logical order", "priority": "P3"},
    {"title": "Session expiry — redirected to login", "steps": "1. Let JWT expire\n2. Attempt any authenticated action", "expected_result": "User redirected to login page with session expired message", "priority": "P1"},
    {"title": "Concurrent edit — optimistic lock", "steps": "1. Open same record in two tabs\n2. Edit and save in both", "expected_result": "Second save shows conflict warning or last-write-wins with notice", "priority": "P2"},
    {"title": "Unsaved changes warning", "steps": "1. Open create form\n2. Fill fields\n3. Navigate away without saving", "expected_result": "Browser prompt warns about unsaved changes", "priority": "P3"},
    {"title": "Sort by column header", "steps": "1. Click a sortable column header\n2. Click again", "expected_result": "List sorted ascending then descending", "priority": "P2"},
    {"title": "API error — server 500 shown gracefully", "steps": "1. Trigger a server error (or mock 500)\n2. Observe UI", "expected_result": "User-friendly error message shown, not raw error or blank", "priority": "P1"},
    {"title": "Accessibility — form labels", "steps": "1. Run axe on the create form", "expected_result": "All inputs have associated labels, no axe violations", "priority": "P3"},
    {"title": "Create with XSS payload in text field", "steps": "1. Enter <script>alert(1)</script> in a text field\n2. Save and view", "expected_result": "Content displayed as literal text, script not executed", "priority": "P1"},
    {"title": "List view loads within 2 seconds", "steps": "1. Navigate to list view with 100 records\n2. Measure page load time", "expected_result": "Page fully interactive within 2 seconds", "priority": "P2"},
    {"title": "Logout clears session", "steps": "1. Click Logout\n2. Attempt to navigate to authenticated route", "expected_result": "User redirected to login, no cached data visible", "priority": "P1"},
    {"title": "Duplicate record detection", "steps": "1. Create a record\n2. Attempt to create another with same unique field", "expected_result": "Conflict error shown, duplicate not created", "priority": "P1"},
    {"title": "Bulk delete", "steps": "1. Select multiple records using checkboxes\n2. Click Delete Selected\n3. Confirm", "expected_result": "All selected records deleted, count shown in confirmation", "priority": "P2"},
    {"title": "Browser back button after delete", "steps": "1. Delete a record\n2. Press browser back button", "expected_result": "Navigates to previous page, deleted record not shown", "priority": "P3"},
    {"title": "Load state on save", "steps": "1. Submit the create form\n2. Observe button state during save", "expected_result": "Save button disabled and shows spinner during API call", "priority": "P2"},
    {"title": "Detail view matches list view data", "steps": "1. Note values in list view\n2. Click to open detail view", "expected_result": "All values match exactly", "priority": "P2"},
    {"title": "Required field asterisk visible", "steps": "1. Open create form\n2. Inspect field labels", "expected_result": "Required fields marked with * or visual indicator", "priority": "P3"},
    {"title": "CSV export of list data", "steps": "1. Click Export/Download CSV on list view", "expected_result": "CSV file downloaded with correct headers and all visible records", "priority": "P2"},
    {"title": "Read permission — view-only user", "steps": "1. Log in as read-only user\n2. Navigate to list view", "expected_result": "Edit and Delete buttons not visible or disabled", "priority": "P1"},
    {"title": "Admin — access all records", "steps": "1. Log in as admin\n2. Navigate to list", "expected_result": "All records visible including other users' records", "priority": "P1"},
    {"title": "Standard user — sees own records only", "steps": "1. Log in as standard user\n2. Navigate to list", "expected_result": "Only records created by this user are visible", "priority": "P1"},
    {"title": "Error boundary — JS crash shown gracefully", "steps": "1. Trigger a React render error (or mock)\n2. Observe UI", "expected_result": "Error boundary shown, rest of page intact", "priority": "P2"},
]

REST_API_CASES = [
    {"title": "POST /auth/login — valid credentials", "steps": "1. POST /auth/login with valid email and password", "expected_result": "200 with access_token in response body", "priority": "P1"},
    {"title": "POST /auth/login — invalid password", "steps": "1. POST /auth/login with valid email, wrong password", "expected_result": "401 Unauthorized with error message", "priority": "P1"},
    {"title": "Protected endpoint — no token", "steps": "1. GET any protected endpoint without Authorization header", "expected_result": "401 Unauthorized", "priority": "P1"},
    {"title": "Protected endpoint — expired token", "steps": "1. Send request with expired JWT in Authorization header", "expected_result": "401 Unauthorized with token expired message", "priority": "P1"},
    {"title": "GET list — returns array", "steps": "1. GET /api/resources with valid token", "expected_result": "200 with JSON array, even if empty", "priority": "P2"},
    {"title": "POST create — valid payload", "steps": "1. POST /api/resources with valid JSON body and auth token", "expected_result": "201 Created with created resource in response", "priority": "P1"},
    {"title": "POST create — missing required field", "steps": "1. POST /api/resources with missing required field", "expected_result": "422 Unprocessable Entity with field-level error", "priority": "P2"},
    {"title": "POST create — invalid field type", "steps": "1. POST /api/resources with wrong type for a field (e.g. string where int expected)", "expected_result": "422 with type validation error", "priority": "P2"},
    {"title": "GET single resource — exists", "steps": "1. GET /api/resources/{id} for existing resource", "expected_result": "200 with full resource object", "priority": "P1"},
    {"title": "GET single resource — not found", "steps": "1. GET /api/resources/{id} for non-existent ID", "expected_result": "404 Not Found", "priority": "P2"},
    {"title": "PUT update — valid payload", "steps": "1. PUT /api/resources/{id} with valid update payload", "expected_result": "200 with updated resource, all changed fields reflected", "priority": "P1"},
    {"title": "PUT update — partial payload (PATCH-style)", "steps": "1. PUT /api/resources/{id} with only some fields", "expected_result": "200 — only specified fields updated, others unchanged", "priority": "P2"},
    {"title": "DELETE resource", "steps": "1. DELETE /api/resources/{id}", "expected_result": "200 or 204, resource no longer returned on GET", "priority": "P1"},
    {"title": "DELETE resource — not found", "steps": "1. DELETE /api/resources/{id} for non-existent ID", "expected_result": "404 Not Found", "priority": "P2"},
    {"title": "Pagination — page and limit params", "steps": "1. GET /api/resources?page=2&limit=10", "expected_result": "Second page of results, total count in response", "priority": "P2"},
    {"title": "Pagination — beyond last page", "steps": "1. GET /api/resources?page=9999&limit=10", "expected_result": "200 with empty array, not 404 or 500", "priority": "P2"},
    {"title": "Rate limiting — too many requests", "steps": "1. Send 10+ requests per second to rate-limited endpoint", "expected_result": "429 Too Many Requests after threshold exceeded", "priority": "P2"},
    {"title": "SQL injection in query param", "steps": "1. GET /api/resources?name=' OR 1=1 --", "expected_result": "No SQL error, no data leak, normal empty/filtered response", "priority": "P1"},
    {"title": "Oversized payload rejected", "steps": "1. POST with request body > 10MB", "expected_result": "413 Payload Too Large", "priority": "P2"},
    {"title": "Concurrent creates — no duplicate IDs", "steps": "1. Send 10 concurrent POST /api/resources requests", "expected_result": "All succeed with unique IDs, no 500 errors", "priority": "P1"},
    {"title": "Response time — GET list < 500ms", "steps": "1. GET /api/resources with 1000 records in DB\n2. Measure response time", "expected_result": "Response received in under 500ms", "priority": "P2"},
    {"title": "Content-Type header validation", "steps": "1. POST without Content-Type: application/json header", "expected_result": "415 Unsupported Media Type or 422", "priority": "P3"},
    {"title": "CORS — preflight OPTIONS request", "steps": "1. Send OPTIONS request from allowed origin", "expected_result": "200 with correct Access-Control-Allow headers", "priority": "P2"},
    {"title": "CORS — disallowed origin blocked", "steps": "1. Send request with Origin: https://evil.com", "expected_result": "CORS headers absent or request rejected", "priority": "P1"},
    {"title": "GET /health returns 200", "steps": "1. GET /health", "expected_result": "200 with {status: ok}", "priority": "P1"},
    {"title": "API versioning — unknown version 404", "steps": "1. GET /api/v99/resources", "expected_result": "404 Not Found", "priority": "P3"},
    {"title": "Filter by field value", "steps": "1. GET /api/resources?status=active", "expected_result": "Only resources with status=active returned", "priority": "P2"},
    {"title": "Sort by field", "steps": "1. GET /api/resources?sort=created_at&order=desc", "expected_result": "Results sorted by created_at descending", "priority": "P2"},
]

MOBILE_CASES = [
    {"title": "App launches without crash", "steps": "1. Cold-launch the app on a supported device", "expected_result": "Splash screen shown, then main screen loads within 3 seconds", "priority": "P1"},
    {"title": "Navigation — tab bar works", "steps": "1. Tap each tab in the bottom navigation bar", "expected_result": "Correct screen shown for each tab, active tab highlighted", "priority": "P1"},
    {"title": "Deep link opens correct screen", "steps": "1. Open a deep link URL from external app", "expected_result": "Correct in-app screen opened", "priority": "P2"},
    {"title": "Back button — Android", "steps": "1. Navigate 3 levels deep\n2. Press Android back button", "expected_result": "Returns to previous screen each time", "priority": "P1"},
    {"title": "Offline mode — cached content shown", "steps": "1. Load app with network\n2. Enable airplane mode\n3. Navigate to cached content", "expected_result": "Cached content visible, offline banner shown", "priority": "P2"},
    {"title": "Offline mode — action blocked gracefully", "steps": "1. Enable airplane mode\n2. Attempt to submit a form", "expected_result": "User-friendly 'No internet connection' message, form preserved", "priority": "P1"},
    {"title": "Network restored — data syncs", "steps": "1. Go offline, make a change\n2. Restore network", "expected_result": "Change synced to server, success confirmation shown", "priority": "P2"},
    {"title": "Push notification — received and tapped", "steps": "1. Send push notification to device\n2. Tap the notification", "expected_result": "App opens to relevant screen", "priority": "P1"},
    {"title": "Push notification — received when app backgrounded", "steps": "1. Background the app\n2. Send push notification", "expected_result": "Notification appears in system tray", "priority": "P2"},
    {"title": "Text input — keyboard does not obscure field", "steps": "1. Tap a text input near bottom of screen\n2. Keyboard appears", "expected_result": "Screen scrolls or input moves above keyboard", "priority": "P2"},
    {"title": "Text input — autocorrect/autocapitalize appropriate", "steps": "1. Type in email field\n2. Type in free-text field", "expected_result": "Email: no autocorrect/autocap. Free-text: autocap on", "priority": "P3"},
    {"title": "Form submission — loading state visible", "steps": "1. Fill form\n2. Tap Submit\n3. Observe button", "expected_result": "Button disabled and spinner shown during API call", "priority": "P2"},
    {"title": "Large list — FlatList scrolls smoothly", "steps": "1. Open a list with 500 items\n2. Scroll quickly up and down", "expected_result": "No jank, no blank cells, 60fps scroll", "priority": "P2"},
    {"title": "Image loading — placeholder shown", "steps": "1. Open screen with remote images on slow network", "expected_result": "Placeholder shown while loading, then replaced by image", "priority": "P3"},
    {"title": "Permission — camera denied gracefully", "steps": "1. Deny camera permission\n2. Attempt to use camera feature", "expected_result": "Explanation shown with link to Settings to grant permission", "priority": "P2"},
    {"title": "App state — resumes correctly after background", "steps": "1. Background the app\n2. Wait 5 minutes\n3. Foreground the app", "expected_result": "App in same state as left, data refreshed if stale", "priority": "P2"},
    {"title": "Session expiry — prompts re-login", "steps": "1. Let session expire (token stale)\n2. Open app or perform action", "expected_result": "User prompted to log in again, no crash", "priority": "P1"},
    {"title": "Accessibility — VoiceOver/TalkBack labels", "steps": "1. Enable VoiceOver/TalkBack\n2. Navigate through main screen", "expected_result": "All interactive elements have meaningful labels", "priority": "P3"},
    {"title": "Accessibility — minimum tap target size", "steps": "1. Inspect all interactive elements", "expected_result": "All tappable elements >= 44x44pt", "priority": "P2"},
    {"title": "Font scaling — large text", "steps": "1. Set OS font size to largest\n2. Navigate through app", "expected_result": "Text scales, no overflow, no truncation of critical labels", "priority": "P3"},
    {"title": "Dark mode — all screens readable", "steps": "1. Enable OS dark mode\n2. Navigate through app", "expected_result": "All text readable, no white-on-white or black-on-black", "priority": "P2"},
    {"title": "App update — migration runs cleanly", "steps": "1. Install previous version and use app\n2. Update to new version", "expected_result": "Existing data preserved, no crash on first launch", "priority": "P1"},
]


def seed_templates():
    db = SessionLocal()
    try:
        for ttype, name, cases in [
            ("react-crud", "React CRUD App", REACT_CRUD_CASES),
            ("rest-api", "REST API", REST_API_CASES),
            ("mobile", "Mobile App", MOBILE_CASES),
        ]:
            if not db.query(Template).filter(Template.type == ttype).first():
                db.add(Template(name=name, type=ttype, cases=cases))
        db.commit()
    finally:
        db.close()
