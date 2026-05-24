from datetime import datetime, timezone


def main() -> None:
    now_utc = datetime.now(timezone.utc)
    print(f"Current UTC time: {now_utc.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Current weekday: {now_utc.strftime('%A')} ({now_utc.weekday()})")
    print("Market mode: crypto 24/7")
    print("In market hours: True")
    print("Note: legacy NYSE/extended-hours checks are deprecated.")


if __name__ == "__main__":
    main()
