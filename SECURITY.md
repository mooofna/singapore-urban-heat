# Security

Please report vulnerabilities privately through
[GitHub security advisories](https://github.com/mooofna/singapore-urban-heat/security/advisories/new)
rather than in a public issue.

The pipeline needs no credentials. The optional `DATAGOVSG_API_KEY` is read from the environment only
and is never logged or written to artifacts. Secrets are kept out of the history by gitleaks in
pre-commit and CI, and notebooks, PDFs and Word files are blocked from commits.
