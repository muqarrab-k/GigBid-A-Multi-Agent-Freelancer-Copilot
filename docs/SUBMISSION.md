# Submission

- **Live URL:** https://gigbid-3g0a.onrender.com
- **GitHub repo:** https://github.com/muqarrab-k/GigBid-A-Multi-Agent-Freelancer-Copilot
- **Report:** `docs/report/REPORT.pdf` (attach the file)
- **Demo video:** https://drive.google.com/file/d/12j2BvMtTN-7vI_BqbtmasswhbHF9h4Ds/view?usp=sharing
- **Portfolio MCP server:**
  - README: https://github.com/muqarrab-k/GigBid-A-Multi-Agent-Freelancer-Copilot/tree/main/mcp_servers/portfolio
  - Docker Hub: https://hub.docker.com/r/mmuq/gigbid-portfolio-mcp
  - Install with uv:
    ```bash
    PORTFOLIO_DIR=~/my-portfolio uvx --from "git+https://github.com/muqarrab-k/GigBid-A-Multi-Agent-Freelancer-Copilot#subdirectory=mcp_servers/portfolio" gigbid-portfolio-mcp
    ```
  - Install with Docker:
    ```bash
    docker run -i --rm -v ~/my-portfolio:/portfolio:ro mmuq/gigbid-portfolio-mcp
    ```
- **Technical write-up:** MEDIUM_LINK
- **Reviewer login:** username reviewer, password in my private Classroom comment
