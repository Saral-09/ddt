# Local web fixture

Start only on loopback:

```bash
python3 server.py
```

Base URL: `http://127.0.0.1:18080/`
Useful paths: `/`, `/health`, `/api/health`, `/about`, `/contact`, `/robots.txt`, `/sitemap.xml`, `/search?q=sample`.

This fixture is deliberately not vulnerable to SQL injection and has no authentication. It is suitable for harmless reachability, crawler, content-discovery and response-handling checks only.
