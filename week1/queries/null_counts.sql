SELECT
    SUM(CASE WHEN job_title IS NULL OR job_title = '' THEN 1 ELSE 0 END),
    SUM(CASE WHEN company IS NULL OR company = '' THEN 1 ELSE 0 END),
    SUM(CASE WHEN description IS NULL OR description = '' THEN 1 ELSE 0 END)
FROM jobs;
