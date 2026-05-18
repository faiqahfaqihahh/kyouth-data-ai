UPDATE jobs
SET quality = CASE
    WHEN description IS NULL OR description = '' THEN 'LOW'
    WHEN job_title IS NULL OR job_title = '' THEN 'LOW'
    WHEN company IS NULL OR company = '' THEN 'LOW'
    WHEN LENGTH(description) < 100 THEN 'LOW'
    WHEN (LENGTH(description) - LENGTH(REPLACE(description, '!', ''))) +
         (LENGTH(description) - LENGTH(REPLACE(description, '#', ''))) > 10 THEN 'LOW'
    ELSE 'HIGH'
END;
