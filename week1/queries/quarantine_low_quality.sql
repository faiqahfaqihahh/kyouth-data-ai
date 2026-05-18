INSERT OR IGNORE INTO jobs_quarantine
SELECT * FROM jobs WHERE quality = 'LOW';
