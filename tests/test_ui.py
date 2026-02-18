import pytest
from playwright.sync_api import Page, expect
import subprocess
import time
import os
import signal
import requests

def wait_for_server(url, timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url + "/_stcore/health")
            if response.status_code == 200:
                return True
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    return False

@pytest.fixture(scope="module")
def streamlit_app():
    # Start the Streamlit app
    # Using 'streamlit run' directly assuming it's in the environment or via uv run
    process = subprocess.Popen(
        ["uv", "run", "streamlit", "run", "app.py", "--server.port", "8502", "--server.headless", "true"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    url = "http://localhost:8502"

    if not wait_for_server(url):
        # Print stderr if failed
        # Use terminate() which works on Windows too
        process.terminate()
        stdout, stderr = process.communicate()
        print(f"Streamlit stdout: {stdout.decode()}")
        print(f"Streamlit stderr: {stderr.decode()}")
        pytest.fail("Streamlit app failed to start")

    yield url

    # Cleanup
    process.terminate()
    process.wait()

def test_app_loads(page: Page, streamlit_app):
    page.goto(streamlit_app)

    # Check page title (Streamlit usually sets it based on set_page_config)
    expect(page).to_have_title("MTF Analytics Dashboard")

    # Check for main header "MTFCK!"
    # Since it is inside an unsafe_allow_html markdown, it might be just text or h1
    # The code: <h1 ...>MTFCK!</h1>
    expect(page.locator("h1", has_text="MTFCK!")).to_be_visible()

    # Check for Sidebar
    expect(page.get_by_test_id("stSidebar")).to_be_visible()

    # Check for "Analysis Controls" in sidebar
    # It is a header: st.header("Analysis Controls")
    expect(page.get_by_role("heading", name="Analysis Controls")).to_be_visible()

    # Check for "Run Analysis" button
    # st.button("Run Analysis", ...)
    # Note: Streamlit buttons are usually inside a button tag with the text
    expect(page.get_by_role("button", name="Run Analysis")).to_be_visible()

    # Check for "Trends" header
    expect(page.get_by_role("heading", name="Trends")).to_be_visible()
