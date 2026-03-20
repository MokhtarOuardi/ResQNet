import httpx
import asyncio
import subprocess
import time
import sys

API_BASE = "http://localhost:8000"

async def test_scan_trends():
    """Call POST /api/monitor/scan_trends and print the result."""
    print("\n" + "=" * 60)
    print("  Testing Function 1: Scan Trends")
    print("=" * 60 + "\n")

    async with httpx.AsyncClient(timeout=120.0) as client:
        print("[*] Calling POST /api/monitor/scan_trends ...")
        resp = await client.post(f"{API_BASE}/api/monitor/scan_trends")

        if resp.status_code != 200:
            print(f"[!] Error {resp.status_code}: {resp.text}")
            return

        data = resp.json()

        print(f"[+] Timestamp: {data['timestamp']}")
        print(f"[+] Trends checked: {data['trends_checked']}")
        print(f"[+] Alerts found: {len(data['alerts'])}\n")

        if not data["alerts"]:
            print("    No disaster-related trends detected at this time.")
        else:
            for i, alert in enumerate(data["alerts"], 1):
                print(f"  --- Alert {i} ---")
                print(f"  Hashtag:       {alert['hashtag']}")
                print(f"  Status:        {alert['status']}")
                print(f"  Disaster Type: {alert.get('disaster_type', 'N/A')}")
                print(f"  Confidence:    {alert['confidence']}")
                print(f"  Reasoning:     {alert['reasoning']}")
                print()

        # Also check status endpoint
        print("-" * 60)
        status_resp = await client.get(f"{API_BASE}/api/monitor/status")
        print(f"[+] Monitor status: {status_resp.json()}")


if __name__ == "__main__":
    asyncio.run(test_scan_trends())
