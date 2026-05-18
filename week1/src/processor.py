import json
import logging
from pathlib import Path

from bs4 import BeautifulSoup

# ── Pydantic data contract ────────────────────────────────────────────────────
try:
    from pydantic import BaseModel, field_validator

    class JobListing(BaseModel):
        source_id:   str
        job_title:   str
        company:     str
        description: str

        @field_validator("source_id", "job_title", "company", "description", mode="before")
        @classmethod
        def must_be_non_empty(cls, v: str) -> str:
            if not isinstance(v, str) or not v.strip():
                raise ValueError("Field must be a non-empty string")
            return v.strip()

        def model_dump(self, **_):
            return {
                "source_id":   self.source_id,
                "job_title":   self.job_title,
                "company":     self.company,
                "description": self.description,
            }

except ImportError:
    # Lightweight fallback when pydantic is not installed (local dev without venv)
    class JobListing:  # type: ignore[no-redef]
        def __init__(self, source_id, job_title, company, description):
            for field, value in [("source_id", source_id), ("job_title", job_title),
                                  ("company", company), ("description", description)]:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"Field '{field}' must be a non-empty string")
            self.source_id   = source_id.strip()
            self.job_title   = job_title.strip()
            self.company     = company.strip()
            self.description = description.strip()

        def model_dump(self):
            return {"source_id": self.source_id, "job_title": self.job_title,
                    "company": self.company, "description": self.description}


logger = logging.getLogger(__name__)


def _extract_fields(soup: BeautifulSoup) -> tuple[str | None, ...]:
    """Return (source_id, job_title, company, description) or None for missing."""
    # source_id – parse the numeric ID from og:url
    source_id = None
    og_url = soup.find("meta", property="og:url")
    if og_url and og_url.get("content"):
        source_id = og_url["content"].rstrip("/").split("?")[0].split("/")[-1]

    # job_title
    title_tag = soup.find(attrs={"data-automation": "job-detail-title"})
    job_title = title_tag.get_text(separator=" ", strip=True) if title_tag else None

    # company – advertiser-name preferred, fallback to company-profile
    company_tag = soup.find(attrs={"data-automation": "advertiser-name"})
    if company_tag:
        company = company_tag.get_text(separator=" ", strip=True)
    else:
        cp = soup.find(attrs={"data-automation": "company-profile"})
        company = cp.get_text(separator=" ", strip=True).split("·")[0].strip() if cp else None

    # description
    desc_tag = soup.find(attrs={"data-automation": "jobAdDetails"})
    description = desc_tag.get_text(separator=" ", strip=True) if desc_tag else None

    return source_id, job_title, company, description


def process_all_html(input_dir: str, output_dir: str) -> None:
    """Clean Bronze HTML files and write validated JSON to the Silver layer."""
    input_path  = Path(input_dir)
    output_path = Path(output_dir)

    print("🥈 Silver:...")

    output_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists() or not any(input_path.iterdir()):
        logger.warning("Bronze directory is empty or does not exist: %s", input_dir)
        print("📊 Silver Summary:")
        print("Total: 0 | Processed: 0 | Skipped: 0")
        return

    html_files = sorted(input_path.glob("*.html"))
    total     = len(html_files)
    processed = 0
    skipped   = 0

    for html_file in html_files:
        try:
            with open(html_file, "r", encoding="utf-8") as fh:
                soup = BeautifulSoup(fh.read(), "html.parser")

            source_id, job_title, company, description = _extract_fields(soup)

            # Report each missing field individually
            missing = {
                "source_id":   source_id,
                "job_title":   job_title,
                "company":     company,
                "description": description,
            }
            skip = False
            for field, value in missing.items():
                if not value:
                    logger.warning("Missing %s in: %s", field, html_file.name)
                    print(f"⚠️  Missing {field} in: {html_file.name}")
                    skip = True

            if skip:
                skipped += 1
                continue

            # Pydantic validation (data contract enforcement)
            listing = JobListing(
                source_id=source_id,
                job_title=job_title,
                company=company,
                description=description,
            )

            # Idempotent write – overwrite existing file
            out_file = output_path / (html_file.stem + ".json")
            with open(out_file, "w", encoding="utf-8") as fh:
                json.dump(listing.model_dump(), fh, ensure_ascii=False, indent=2)

            logger.info("Processed: %s", html_file.name)
            print(f"✅ Processed: {html_file.name}")
            processed += 1

        except ValueError as exc:
            logger.error("Validation error in %s | Reason: %s", html_file.name, exc)
            skipped += 1
        except Exception as exc:
            logger.error("Error processing %s | Reason: %s", html_file.name, exc)
            skipped += 1

    print("📊 Silver Summary:")
    print(f"Total: {total} | Processed: {processed} | Skipped: {skipped}")