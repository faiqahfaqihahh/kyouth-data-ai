import email
import quopri
from pathlib import Path


def ingest_all_mhtml(input_dir, output_dir):
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    print("🥉 Bronze:...")

    # Idempotency: create output dir if missing
    output_path.mkdir(parents=True, exist_ok=True)

    # Idempotency: handle missing/empty source dir gracefully
    if not input_path.exists() or not any(input_path.iterdir()):
        print("⚠️  Source directory is empty or does not exist.")
        print("📊 Bronze Summary:")
        print("Total: 0 | Extracted: 0 | Failed: 0")
        return

    mhtml_files = list(input_path.glob("*.mhtml"))
    total = len(mhtml_files)
    extracted = 0
    failed = 0

    for mhtml_file in mhtml_files:
        try:
            with open(mhtml_file, "rb") as f:
                msg = email.message_from_bytes(f.read())

            html_content = None
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_content = payload.decode("utf-8", errors="replace")
                    break

            if not html_content:
                print(f"⚠️  No HTML content found in: {mhtml_file.name}")
                failed += 1
                continue

            output_file = output_path / (mhtml_file.stem + ".html")
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(html_content)

            print(f"✅ Extracted: {mhtml_file.name}")
            extracted += 1

        except Exception as e:
            print(f"❌ Error processing {mhtml_file.name}: {e}")
            failed += 1

    print("📊 Bronze Summary:")
    print(f"Total: {total} | Extracted: {extracted} | Failed: {failed}")