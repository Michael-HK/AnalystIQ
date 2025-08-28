# AgentInvest PoC

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AgentInvest** is an AI-powered investment analysis platform that automatically generates comprehensive financial reports for stock analysis. This Proof of Concept (PoC) demonstrates the integration of advanced AI models, web scraping, financial data APIs, and automated report generation to create professional-grade investment research documents.

## 🚀 Key Features

- **Automated Investment Research**: Generates comprehensive 6-10 page investment reports with minimal user input
- **Multi-Source Data Integration**: Combines real-time web search, financial APIs, and market data
- **AI-Powered Analysis**: Leverages Google's Gemini models for intelligent content generation and analysis
- **Professional Report Generation**: Produces publication-ready PDF reports with charts, tables, and citations
- **Interactive Web Interface**: User-friendly Streamlit application for easy report generation
- **Caching System**: Redis-based caching for improved performance and reduced API calls
- **Containerized Deployment**: Docker support for easy deployment and scalability

## 📊 Report Structure

Each generated report follows a professional investment analysis structure:

1. **Executive Summary** - Key findings and investment outlook
2. **Company Overview** - Business model and core operations
3. **Industry & Competitive Analysis** - Market positioning and competitive moat
4. **Financial Performance** - Deep dive into financial statements and KPIs
5. **Growth Catalysts** - Future opportunities and growth drivers
6. **Valuation Assessment** - Current valuation vs peers and intrinsic value
7. **Risk Analysis** - Potential risks and mitigation strategies
8. **Investment Conclusion** - Final recommendation and outlook

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Streamlit UI  │────│  AgentInvest     │────│  Report Engine  │
│                 │    │     Core         │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
        ┌───────▼──────┐ ┌──────▼──────┐ ┌─────▼──────┐
        │ Web Search   │ │ Financial   │ │  AI Models │
        │   (Tavily)   │ │ Data (YF)   │ │  (Gemini)  │
        └──────────────┘ └─────────────┘ └────────────┘
```

## 🛠️ Technology Stack

### Core Technologies
- **Python 3.10+** - Primary programming language
- **Streamlit** - Web application framework
- **Google Gemini** - AI language models (2.0-flash, 2.5-flash)
- **LlamaIndex** - AI agent framework and tools

### Data Sources
- **Yahoo Finance (yfinance)** - Financial data and market information
- **Tavily API** - Web search and content extraction
- **Trafilatura** - Web content extraction and cleaning

### Report Generation
- **Markdown2** - Markdown to HTML conversion
- **wkhtmltopdf** - PDF generation from HTML
- **Chart.js** - Interactive chart generation
- **html2image** - Chart rendering for PDF embedding

### Infrastructure
- **Redis** - Caching layer for performance optimization
- **Docker** - Containerization and deployment
- **Docker Compose** - Multi-service orchestration

## 📋 Prerequisites

### Required API Keys
- **Google Cloud Platform** - For Gemini AI models access
- **Tavily API** - For web search capabilities

### System Requirements
- Python 3.10 or higher
- Docker and Docker Compose (for containerized deployment)
- 4GB+ RAM recommended
- Internet connection for API access

## 🚀 Quick Start

### Option 1: Docker Deployment (Recommended)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd PoC_AgentInvest
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Configure Google Cloud credentials**
   - Place your `Midas-Gemini-IAM-Admin.json` service account file in the project root
   - Ensure the service account has Vertex AI access

4. **Launch with Docker Compose**
   ```bash
   docker-compose up -d
   ```

5. **Access the application**
   - Open your browser to `http://localhost:8501`
   - Select a stock ticker and generate your first report!

### Option 2: Local Development

1. **Install system dependencies**
   ```bash
   # Ubuntu/Debian
   sudo apt-get update && sudo apt-get install -y wkhtmltopdf
   
   # macOS
   brew install wkhtmltopdf
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   export TAVILY_API_KEY="your-tavily-api-key"
   export GOOGLE_APPLICATION_CREDENTIALS="./Midas-Gemini-IAM-Admin.json"
   ```

4. **Run the Streamlit application**
   ```bash
   streamlit run streamlit_app.py
   ```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TAVILY_API_KEY` | API key for Tavily web search | Yes |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Google Cloud service account JSON | Yes |
| `CHARTJS_SRC` | Chart.js library source URL | No (defaults to CDN) |
| `REDIS_URL` | Redis connection URL for caching | No (defaults to localhost) |

### Supported Stock Tickers

The application supports:
- **US Stocks**: AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA, etc.
- **Hong Kong Stocks**: 0001.HK, 0002.HK, etc. (200+ tickers)

## 📖 Usage Examples

### Command Line Interface
```bash
# Generate report for Apple Inc.
python -m main AAPL

# Generate report for Microsoft
python -m main MSFT
```

### Web Interface
1. Navigate to the Streamlit application
2. Select a stock ticker from the dropdown
3. Click "Generate Report"
4. Monitor progress in real-time
5. Download the generated PDF report

### Programmatic Usage
```python
from agent import AgentInvest
import asyncio

async def generate_report():
    agent = AgentInvest(verbose_agent=False)
    report = await agent.run(ticker="AAPL")
    return report

# Run the async function
report = asyncio.run(generate_report())
```

## 🔧 Advanced Configuration

### Custom Report Structure
Modify the prompts in `prompts.py` to customize report sections and analysis depth.

### AI Model Configuration
Adjust model parameters in `agent.py`:
```python
self.llm = VertexAI(
    model="gemini-2.0-flash",
    temperature=1,
    max_tokens=8000
)
```

### Caching Configuration
Configure Redis caching in `cache_manager.py`:
```python
cache_manager = RedisCacheManager(ttl_seconds=3600)  # 1 hour cache
```

## 📁 Project Structure

```
PoC_AgentInvest/
├── agent.py                 # Core AgentInvest class
├── streamlit_app.py         # Web interface
├── main.py                  # CLI entry point
├── prompts.py               # AI prompts and templates
├── utils.py                 # PDF generation utilities
├── utils_v2.py             # Enhanced PDF utilities
├── cache_manager.py         # Redis caching layer
├── gemini_vertex.py         # Vertex AI integration
├── plot_utils.py           # Chart generation utilities
├── tickers.py              # Supported stock tickers
├── requirements.txt         # Python dependencies
├── Dockerfile              # Container configuration
├── docker-compose.yml      # Multi-service setup
├── tools/                  # Specialized tools
│   ├── web_search.py       # Tavily web search
│   ├── financial_tools.py  # Yahoo Finance integration
│   └── __init__.py
└── generated_reports/      # Output directory for reports
```

## 🔍 Key Components

### AgentInvest Core (`agent.py`)
The main orchestrator that coordinates data gathering, AI analysis, and report generation.

### Web Search Tool (`tools/web_search.py`)
Handles web search queries using Tavily API for current market information and news.

### Financial Tools (`tools/financial_tools.py`)
Integrates with Yahoo Finance for historical data, financial statements, and company information.

### Report Generation (`utils.py`, `utils_v2.py`)
Converts Markdown reports with embedded charts into professional PDF documents.

### Caching System (`cache_manager.py`)
Redis-based caching to improve performance and reduce API costs.

## 🚦 Performance Optimization

- **Parallel Processing**: Web and financial data queries run concurrently
- **Intelligent Caching**: Redis caching reduces redundant API calls
- **Batch Processing**: Report sections generated in optimized batches
- **Resource Management**: Configurable rate limiting and timeout handling

## 🔒 Security Considerations

- **API Key Management**: Environment variables for secure credential storage
- **Input Validation**: Ticker symbol validation and sanitization
- **PDF Generation**: Secure HTML-to-PDF conversion with sandboxing
- **Network Security**: Containerized deployment with network isolation

## 🐛 Troubleshooting

### Common Issues

**PDF Generation Fails**
```bash
# Verify wkhtmltopdf installation
wkhtmltopdf --version

# Check system dependencies
docker exec -it container_name wkhtmltopdf --version
```

**API Rate Limiting**
- Implement delays between requests
- Check API quota limits
- Verify API key validity

**Memory Issues**
- Increase Docker memory limits
- Monitor memory usage during report generation
- Consider processing reports in smaller batches

### Debugging

Enable verbose logging:
```python
agent = AgentInvest(verbose_agent=True)
```

Check container logs:
```bash
docker-compose logs -f poc-agentinvest-app
```

## 📈 Future Enhancements

- **Multi-language Support**: Localized reports in different languages
- **Advanced Charting**: Interactive charts with drill-down capabilities
- **Portfolio Analysis**: Multi-stock portfolio optimization reports
- **Real-time Updates**: Live data streaming and report updates
- **Custom Templates**: User-defined report templates and branding
- **API Endpoints**: RESTful API for programmatic access

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Google Cloud Platform** for Vertex AI and Gemini models
- **Tavily** for web search API services
- **Yahoo Finance** for financial data access
- **Streamlit** for the web application framework
- **LlamaIndex** for AI agent orchestration

## 📞 Support

For questions, issues, or contributions:
- Create an issue in the repository
- Review the troubleshooting section above
- Check the project documentation

---

**Disclaimer**: This is a Proof of Concept for demonstration purposes. The generated reports are for informational use only and should not be considered as financial advice. Always consult with qualified financial professionals before making investment decisions.
