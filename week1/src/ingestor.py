from pathlib import Path
import logging

def ingest_all_mhtml(input_dir, output_dir): 
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

def decode_mhtml(raw_bytes: bytes) -> str:
    try:
        decoded_bytes = quopri.decodestring(raw_bytes)
        return decoded_bytes.decode('utf-8', errors='ignore')
    except Exception:
        return raw_bytes.decode('utf-8', errors='ignore')

    total, extracted, failed = 0, 0, 0

    for mhtml_file in input_dir.glob("*.mhtml"):
        total += 1
        try:
            raw_text = mhtml_file.read_text(encoding="utf-8", errors="ignore")

            html_start = raw_text.find("<html")
            html_end = raw_text.find("</html>", html_start)
            if html_start != -1 and html_end != -1:
                html_content = raw_text[html_start:html_end + len("</html>")]
                out_file = output_dir / (mhtml_file.stem + ".html")
                out_file.write_text(html_content, encoding="utf-8")
                print(f"✅ Extracted: {mhtml_file.name}")
                logging.info(f"Extracted: {mhtml_file.name}")
                extracted += 1
            else:
                print(f"⚠️ No HTML tags found in: {mhtml_file.name}")
                logging.warning(f"No HTML tags found in: {mhtml_file.name}")
                failed += 1
            
        except Exception as e:
            print(f"❌ Failed to process {mhtml_file.name}: {e}")
            logging.error(f"Failed to process {mhtml_file.name}: {e}")
            failed += 1

    print("\n📊 Bronze Summary:")
    print(f"Total: {total} | Extracted: {extracted} | Failed: {failed}")