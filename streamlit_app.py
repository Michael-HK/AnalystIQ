
import streamlit as st
import asyncio
import os
import base64
from datetime import datetime
from agent import AgentInvest
from tickers import TICKERS

# --- Page Configuration ---
st.set_page_config(
    page_title="AgentInvest PoC",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="auto",
)

# --- App Styling ---
st.markdown("""
    <style>
        .reportview-container { background: #f0f2f6; }
        .sidebar .sidebar-content { background: #ffffff; }
        .stButton>button {
            color: #ffffff; background-color: #0068c9; border-radius: 5px;
            border: none; padding: 10px 20px;
        }
        .stButton>button:hover { background-color: #005aa3; }
        .stDownloadButton>button {
            color: #ffffff; background-color: #28a745; border-radius: 5px;
            border: none; padding: 10px 20px;
        }
        .stDownloadButton>button:hover { background-color: #218838; }
        .generated-item {
            border-left: 4px solid #0068c9;
            padding-left: 10px;
            margin-bottom: 10px;
        }
    </style>
""", unsafe_allow_html=True)

# --- Helper Functions ---
def get_pdf_download_link(file_path, link_text):
    """Generates a link to download a file."""
    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    href = f'<a href="data:application/octet-stream;base64,{data}" download="{os.path.basename(file_path)}">{link_text}</a>'
    return href

# --- Main Application ---
def main():
    st.title("📈 AgentInvest PoC")
    
    # Updated intro copy based on feedback
    st.markdown("""
    Hi, I'm **AgentInvest** — your AI-powered investing companion.
    
    To show you what I can do, I've included a few stock tickers for you to pick from. Once you select one and click **Generate Report**, I'll get to work:
    
    • Researching the company and its market trends  
    • Analyzing relevant financial and industry information  
    • Compiling everything into a detailed investment report
    
    Go ahead, choose a ticker and let me start the analysis for you. 🚀
    """)

    st.sidebar.header("Configuration")
    
    selected_ticker = st.sidebar.selectbox("Select a Stock Ticker:", TICKERS)

    # Initialize session state variables
    if 'report_generated' not in st.session_state:
        st.session_state.report_generated = False
        st.session_state.pdf_path = ""
        st.session_state.progress_log = []
        st.session_state.generated_data = {}
        st.session_state.is_running = False

    # --- UI Placeholders ---

    structure_area = st.container()
    query_cols = st.columns(2)
    web_queries_area = query_cols[0]
    financial_queries_area = query_cols[1]
    progress_area = st.empty()
    
    if st.sidebar.button("Generate Report", disabled=st.session_state.is_running):
        # Reset state for a new runSS
        st.session_state.report_generated = False
        st.session_state.pdf_path = ""
        st.session_state.progress_log = []
        st.session_state.generated_data = {}
        st.session_state.is_running = True

        def update_ui(payload: dict):
            message = payload.get("message", "")
            data = payload.get("data")

            # Update the main progress log and redraw the UI in the placeholder
            st.session_state.progress_log.append(message)
            
            with progress_area.container():
                st.subheader("Agent Progress")
                for i, log in enumerate(st.session_state.progress_log):
                    # Use different styling for completed vs current steps
                    if i == len(st.session_state.progress_log) - 1 and st.session_state.is_running:
                        st.success(f"🔄 {log}")
                    else:
                        st.info(f"✅ {log}")
            
            # Update specific data sections
            if "structure generated" in message and data:
                st.session_state.generated_data['structure'] = data
                with structure_area:
                    st.subheader("Generated Report Structure")
                    st.json(data)
            
            if "web search queries" in message and data:
                st.session_state.generated_data['web_queries'] = data
                with web_queries_area:
                    st.subheader("Generated Web Queries")
                    for q in data:
                        st.markdown(f"<div class='generated-item'>{q}</div>", unsafe_allow_html=True)

            if "financial data queries" in message and data:
                st.session_state.generated_data['financial_queries'] = data
                with financial_queries_area:
                    st.subheader("Generated Financial Queries")
                    for q in data:
                        st.markdown(f"<div class='generated-item'>{q['query']} ({q['ticker']})</div>", unsafe_allow_html=True)
        
        with st.spinner("AgentInvest is now conducting research... Please wait."):
            try:
                # Add explicit debug logging
            #    st.info("🔧 Initializing AgentInvest agent...")
                agent = AgentInvest(verbose_agent=False)
            #    st.info("✅ Agent initialized successfully. Starting report generation...")
                
                asyncio.run(agent.run(ticker=selected_ticker, progress_callback=update_ui))

                st.session_state.report_generated = True
                st.session_state.pdf_path = f"generated_reports/{selected_ticker}_AgentInvest_Report.pdf"

            except Exception as e:
                # Make the error much more visible
                st.error(f"❌ CRITICAL ERROR: {str(e)}")
                st.error(f"Error type: {type(e).__name__}")
                # Print to console for debugging
                print(f"Streamlit Exception: {e}")
                import traceback
                traceback.print_exc()
            
            finally:
                st.session_state.is_running = False


        with progress_area.container():
            st.subheader("Agent Progress")
            for log in st.session_state.progress_log:
                st.info(f"✅ {log}") 

        if st.session_state.report_generated:
            st.success("Report generation complete!")
        else:
            st.error("Report generation failed. Please review the progress log.")
        
        st.rerun()


    if not st.session_state.is_running and not st.session_state.progress_log:
        progress_area.info("Select a stock ticker from the sidebar and click 'Generate Report' to begin.")
    elif not st.session_state.is_running and st.session_state.progress_log:
        # Maintain the final progress display after completion
        with progress_area.container():
            st.subheader("Agent Progress")
            for log in st.session_state.progress_log:
                st.info(f"✅ {log}") 

    # Show download section prominently after completion
    if st.session_state.report_generated and not st.session_state.is_running:
        st.markdown("---")
        st.success("🎉 **Report Generation Complete!**")
        
        # Create a prominent download section
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.subheader("📄 Download Your Investment Report")
            if os.path.exists(st.session_state.pdf_path):
                # Creating download button
                st.markdown(f"""
                <div style="text-align: center; padding: 20px; background-color: #f0f2f6; border-radius: 10px; margin: 10px 0;">
                    <h4 style="color: #1f77b4;">Your Investment Report is Ready!</h4>
                    <p>Click the button below to download your comprehensive analysis.</p>
                    {get_pdf_download_link(st.session_state.pdf_path, "📥 Download PDF Report")}
                </div>
                """, unsafe_allow_html=True)
                
                # Show file info
                file_size = os.path.getsize(st.session_state.pdf_path) / 1024  # KB
                st.info(f"📊 Report size: {file_size:.1f} KB | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            else:
                st.error("❌ Could not find the generated PDF file. The report may have failed to generate correctly.")
                
    elif st.session_state.report_generated and st.session_state.is_running:
        # Show a temporary message while still processing
        st.info("🔄 Finalizing your report...")

if __name__ == "__main__":
    main()
