import asyncio
import logging
import os
import sys
from datetime import datetime

# Set UTF-8 encoding for Windows BEFORE any other imports
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_models.oci_generative_ai import ChatOCIGenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

import phoenix as px
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(process)d - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from config_loader import load_properties, ensure_oci_config, apply_db_env, get_oci_llm_params

# Load and apply configuration before any SDK usage
PROPS = load_properties(os.path.join(os.getcwd(), 'config.properties'))
ensure_oci_config(PROPS)
apply_db_env(PROPS)

# 1. Start Phoenix (it opens the OTLP server on port 6006)
logger.info("Starting Phoenix observability platform...")
px.launch_app()
logger.info("✅ Phoenix launched on http://localhost:6006")

# 2. Configure OpenTelemetry
resource = Resource(attributes={"service.name": "ollama_oraclegenai_trace"})
provider = TracerProvider(resource=resource)
trace.set_tracer_provider(provider)

# 3. Configure the exporter to send spans to Phoenix
otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:6006/v1/traces")
span_processor = BatchSpanProcessor(otlp_exporter)
provider.add_span_processor(span_processor)

# 4. Create the tracer
tracer = trace.get_tracer(__name__)

class MemoryState:
    def __init__(self):
        self.messages = []

# Define the language model using config.properties
_llm_params = get_oci_llm_params(PROPS)
llm = ChatOCIGenAI(
    model_id=_llm_params['model_id'],
    service_endpoint=_llm_params['service_endpoint'],
    compartment_id=_llm_params['compartment_id'],
    auth_profile="DEFAULT",
    model_kwargs={"temperature": 0.1, "top_p": 0.75, "max_tokens": 2000}
)

# Try to make console UTF-8 on Windows to avoid emoji crashes from dependencies
for handler in logging.root.handlers:
    if isinstance(handler, logging.StreamHandler):
        try:
            if hasattr(handler.stream, 'reconfigure'):
                handler.stream.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
        except Exception:
            pass

# Prompt
prompt = ChatPromptTemplate.from_messages([
    ("system", """
        You are an agent responsible for resolving inconsistencies in customer return invoices.
        
        Your goal is to find the original outbound invoice issued by the company,
        based on the information from the customer's return invoice.
        ### Important:
        
        1. Use the `InvoiceItemResolver` server for all queries.
        
        2. First, use the **vector or fuzzy search** tool (search_vectorized_product) to find the **most likely EAN**, 
        based on the product description provided by the customer. The `code` attribute from the vector search result 
        can be interpreted as the EAN.
        
        3. Use `resolve_ean` to obtain the most probable EAN. If it returns a dictionary with an error, halt the operation.
        
        4. Only after finding a valid EAN, use the tool `search_invoices_by_criteria` to search for the original outbound invoice.
        
           - Use the EAN along with customer name, price, and location (state) for the search.
        
        ### Example input:
        
        ```json
        {{
          "customer": "Customer 43",
          "description": "Harry Poter",
          "price": 139.55,
          "location": "RJ"
        }}
        
        If a corresponding outbound invoice is found, return:
        
            • invoice number,
        
            • customer name,
        
            • state,
        
            • EAN,
        
            • product description,
        
            • unit price.
        
        If no match is found, respond exactly with:
        “EAN not found with the provided criteria.”
    """),
    ("placeholder", "{messages}")
])

# Run the client with the MCP server
async def main():
    logger.info("="*60)
    logger.info("Initializing OCI GenAI Bot MCP Client")
    logger.info("="*60)
    
    async with MultiServerMCPClient(
            {
                "InvoiceItemResolver": {
                    "command": "python",
                    "args": ["-u", "server_invoice_items.py"],
                    "transport": "stdio",
                },
            }
    ) as client:
        tools = client.get_tools()
        if not tools:
            logger.error("❌ No MCP tools were loaded. Please check if the server is running.")
            print("❌ No MCP tools were loaded. Please check if the server is running.")
            return

        logger.info(f"🛠️ Loaded tools: {[t.name for t in tools]}")
        print("🛠️ Loaded tools:", [t.name for t in tools])

        # Creating the LangGraph agent with in-memory state
        memory_state = MemoryState()

        agent_executor = create_react_agent(
            model=llm,
            tools=tools,
            prompt=prompt,
        )

        logger.info("🤖 Agent ready to process queries")
        print("🤖 READY")
        while True:
            query = input("You: ")
            if query.lower() in ["quit", "exit"]:
                logger.info("User requested exit")
                break
            if not query.strip():
                continue

            logger.info(f"Processing user query: {query[:100]}...")
            memory_state.messages.append(HumanMessage(content=query))
            try:
                result = await agent_executor.ainvoke({"messages": memory_state.messages})
                new_messages = result.get("messages", [])

                # Store new messages
                # memory_state.messages.extend(new_messages)
                memory_state.messages = []

                response_content = new_messages[-1].content
                # Normalize response content to string
                if isinstance(response_content, list):
                    try:
                        response_text = "".join([
                            (part.get("text", "") if isinstance(part, dict) else str(part))
                            for part in response_content
                        ])
                    except Exception:
                        response_text = str(response_content)
                else:
                    response_text = str(response_content)

                logger.info(f"Generated response: {response_text[:100]}...")
                # Emit clear markers for external UIs to read multi-line responses fully
                print("ASSIST_BEGIN")
                print(response_text)
                print("ASSIST_END")

                formatted_messages = prompt.format_messages()

                # Converting each message to a string
                formatted_messages_str = "\n".join([str(msg) for msg in formatted_messages])
                with tracer.start_as_current_span("Server NF Items") as span:
                    # Append the prompt and response as attributes to the trace
                    span.set_attribute("llm.prompt", formatted_messages_str)
                    span.set_attribute("llm.response", response_text)
                    span.set_attribute("llm.model", "ocigenai")

                    executed_tools = []
                    if "intermediate_steps" in result:
                        for step in result["intermediate_steps"]:
                            tool_call = step.get("tool_input") or step.get("action")
                            if tool_call:
                                tool_name = tool_call.get("tool") or step.get("tool")
                                if tool_name:
                                    executed_tools.append(tool_name)

                    if not executed_tools:
                        executed_tools = [t.name for t in tools]  # fallback

                    span.set_attribute("llm.executed_tools", ", ".join(executed_tools))

            except Exception as e:
                logger.error(f"Error processing query: {e}", exc_info=True)
                print("Error:", e)

# Run the agent with asyncio
if __name__ == "__main__":
    logger.info("="*60)
    logger.info(f"Starting OCI GenAI Bot - {datetime.now()}")
    logger.info("="*60)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
    finally:
        logger.info("Application shutdown complete")