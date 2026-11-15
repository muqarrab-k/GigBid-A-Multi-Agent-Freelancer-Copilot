FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY gigbid_portfolio_mcp ./gigbid_portfolio_mcp
RUN pip install --no-cache-dir . && useradd --create-home app
USER app
ENV PORTFOLIO_DIR=/portfolio
# stdio by default
ENTRYPOINT ["gigbid-portfolio-mcp"]
