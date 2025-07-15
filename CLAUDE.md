## testing and environment
- We are on a local development environment using Docker. The main container is called `app`.
- Run tests on the 'app' container: `docker compose exec app pytest`

## Style Guide
- Use [Black](https://github.com/ambv/black) for code formatting (120 char line length)
- Import ordering: Use isort (stdlib, django, third-party, local)
- Place imports at the top of the file unless necessary to import them later due to circular imports
