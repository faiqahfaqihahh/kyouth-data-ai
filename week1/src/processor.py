from pathlib import Path
from bs4 import BeautifulSoup
from pydantic import BaseModel
import json
import quopri
import logging

class JobListing(BaseModel):
    source_id: str
    job_title: str
    company: str
    description: str

def decode_mhtml(raw_bytes: bytes) -> str:
    try:
        decoded_bytes = quopri.decodestring(raw_bytes)
        return decoded_bytes.decode('utf-8', errors='ignore')
    except Exception:
        return raw_bytes.decode('utf-8', errors='ignore')

def process_all_html(input_dir, output_dir): 
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total, processed, skipped = 0, 0, 0

    for html_file in input_dir.glob("*.html"):
        total += 1
        try:
            raw_bytes = html_file.read_bytes()
            html_str = decode_mhtml(raw_bytes)
            soup = BeautifulSoup(html_str, "html.parser")

            url_tag = soup.find("meta", property="og:url")
            source_id = url_tag["content"].rstrip("/").split("/")[-1] if url_tag else None

            title_tag = soup.find(attrs={"data-automation": "job-detail-title"})
            job_title = title_tag.get_text(separator=" ", strip=True) if title_tag else None
 
            desc_tag = soup.find(attrs={"data-automation": "jobAdDetails"})
            description = desc_tag.get_text(separator=" ", strip=True) if desc_tag else None
 
            company_tag = soup.find(attrs={"data-automation": "advertiser-name"})
            company = company_tag.get_text(separator=" ", strip=True) or None

            if source_id and job_title and company and description:
                job_listing = JobListing(
                    source_id=source_id,
                    job_title=job_title,
                    company=company,
                    description=description
                )
                out_file = output_dir / (html_file.stem + ".json")
                out_file.write_text(json.dumps(job_listing.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"✅ Processed: {html_file.name}")
                logging.info(f"Processed: {html_file.name}")
                processed += 1
            else:
                if not source_id:
                    print(f"⚠️ Missing source_id in: {html_file.name}")
                    logging.warning(f"Missing source_id in: {html_file.name}")
                if not job_title:
                    print(f"⚠️ Missing job_title in: {html_file.name}")
                    logging.warning(f"Missing job_title in: {html_file.name}")
                if not company:
                    print(f"⚠️ Missing company in: {html_file.name}") 
                    logging.warning(f"Missing company in: {html_file.name}") 
                if not description:
                    print(f"⚠️ Missing description in: {html_file.name}")  
                    logging.warning(f"Missing description in: {html_file.name}") 
                skipped += 1

        except Exception as e:
            print(f"❌ Failed to process {html_file.name}: {e}")
            logging.error(f"Failed to process {html_file.name}: {e}")
            skipped += 1
            
    print(f"\n📊 Silver Summary:")
    print(f"\n Total={total}, Processed={processed}, Skipped={skipped}")