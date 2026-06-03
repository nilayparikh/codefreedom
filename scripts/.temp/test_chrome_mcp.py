import http.client
import json
import socket
import sys

TARGET_HOST = "127.0.0.1"
TARGET_PORT = 9222
TARGET_PATH = "/json/version"


def test_chrome_debugging():
    print(f"=== Checking Connection to {TARGET_HOST}:{TARGET_PORT} ===")

    # 1. Test Raw TCP Socket Connection
    try:
        with socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=2.0):
            print(f"✅ Connection successful: Port {TARGET_PORT} is open.")
    except (socket.timeout, ConnectionRefusedError):
        print(f"❌ Connection failed: Port {TARGET_PORT} is closed.")
        print("👉 Ensure Chrome is running with: --remote-debugging-port=9222")
        sys.exit(1)

    # 2. Test HTTP Endpoint Response
    print(f"\n=== Fetching DevTools Endpoint: {TARGET_PATH} ===")
    try:
        conn = http.client.HTTPConnection(TARGET_HOST, TARGET_PORT, timeout=2.0)
        conn.request("GET", TARGET_PATH)
        response = conn.getresponse()
        status_code = response.status
        response_data = response.read().decode("utf-8")
        conn.close()

        if status_code == 200:
            try:
                data = json.loads(response_data)
                print("✅ Success! DevTools endpoint responded correctly.")
                print(f"🌐 Browser Version: {data.get('Browser', 'Unknown')}")
                print(
                    f"🔗 WebSocket URL:   {data.get('webSocketDebuggerUrl', 'Missing')}"
                )
                print("\n🎉 Setup looks perfect for the '--browser-url' config option!")
            except json.JSONDecodeError:
                print(
                    "❌ Error: Response was received but could not be parsed as valid JSON."
                )
                sys.exit(1)

        elif status_code == 404:
            print(f"⚠️ Warning: Endpoint returned HTTP {status_code}.")
            print(
                "👉 Your port is open, but recent Chrome security profiles are restricting raw HTTP requests."
            )
            print(
                "💡 Fix: Update your '.claude.json' to use '--autoConnect' instead of '--browser-url'."
            )

        else:
            print(f"❌ Error: Endpoint returned unexpected status code {status_code}.")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Network request failure: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    test_chrome_debugging()
