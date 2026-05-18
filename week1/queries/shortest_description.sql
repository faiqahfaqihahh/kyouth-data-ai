SELECT source_id, job_title, LENGTH(description) AS len
FROM jobs
WHERE description IS NOT NULL
ORDER BY len ASC
LIMIT 1;
