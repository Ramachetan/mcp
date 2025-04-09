import json
import os
import chainlit as cl
from dotenv import load_dotenv
from openai import AsyncOpenAI
from mcp import ClientSession # Assuming this is correctly imported for Chainlit MCP

# --- Configuration ---
load_dotenv()

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise ValueError("API_KEY not found in environment variables.")

BASE_URL = os.getenv("BASE_URL")
if not BASE_URL:
    raise ValueError("BASE_URL not found in environment variables.")

# Initialize OpenAI client pointing to Gemini endpoint
# Use AsyncOpenAI for compatibility with Chainlit's async nature
client = AsyncOpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

# Select your desired Gemini model
MODEL_NAME = "gemini-2.0-flash"

print(f"Using model: {MODEL_NAME}")

def get_system_prompt():
    """Read the system prompt from file, ensuring we always get the latest version."""
    with open("system.md", "r") as f:
        return f.read()

# Helper to flatten nested lists
def flatten(xss):
    """Flattens a list of lists into a single list."""
    return [x for xs in xss for x in xs]

@cl.on_mcp_connect
async def on_mcp_connect(connection, session: ClientSession):
    """
    Called when a user connects to an MCP server.
    Discovers tools and stores their metadata.
    """
    print(f"Attempting to connect to MCP: {connection.name}")
    try:
        result = await session.list_tools()
        # Store MCP tool metadata, including which connection it belongs to
        tools_metadata = [{
            "name": t.name,
            "description": t.description,
            "input_schema": t.inputSchema, # Keep original schema for later formatting
            "mcp_connection_name": connection.name
        } for t in result.tools]

        # Store tools grouped by connection name in user session
        mcp_tools = cl.user_session.get("mcp_tools", {})
        mcp_tools[connection.name] = tools_metadata
        cl.user_session.set("mcp_tools", mcp_tools)

        tool_names = [t['name'] for t in tools_metadata]
        print(f"Connected to MCP '{connection.name}' and found tools: {tool_names}")

    except Exception as e:
        print(f"Error connecting/listing tools for MCP '{connection.name}': {e}")
        await cl.ErrorMessage(f"Failed to list tools from MCP server '{connection.name}': {e}").send()

@cl.on_mcp_disconnect
async def on_mcp_disconnect(name: str, session: ClientSession):
    """
    Called when an MCP connection is closed. Removes associated tools.
    """
    print(f"MCP Connection '{name}' disconnected.")
    mcp_tools = cl.user_session.get("mcp_tools", {})
    if name in mcp_tools:
        del mcp_tools[name]
        cl.user_session.set("mcp_tools", mcp_tools)
        print(f"Removed tools associated with connection '{name}'.")

@cl.step(type="tool")
async def call_mcp_tool(tool_call):
    """
    Executes a specific tool call requested by the LLM via the correct MCP session.
    Updates the Chainlit UI step with execution details.
    """
    tool_name = tool_call.function.name
    current_step = cl.context.current_step
    current_step.name = tool_name # Set step name in UI early

    try:
        # Arguments are provided as a JSON string by the LLM
        tool_input = json.loads(tool_call.function.arguments)
        current_step.input = tool_input # Show input arguments in UI
    except json.JSONDecodeError:
        error_msg = f"Error: Invalid JSON arguments received for tool {tool_name}: {tool_call.function.arguments}"
        print(error_msg)
        current_step.output = json.dumps({"error": error_msg})
        current_step.is_error = True
        return json.dumps({"error": error_msg}) # Return error string for LLM

    print(f"Attempting to call MCP tool: {tool_name} with args: {tool_input}")

    # --- Find the correct MCP connection and session for the tool ---
    mcp_tools_by_connection = cl.user_session.get("mcp_tools", {})
    mcp_connection_name = None
    for conn_name, tools_metadata in mcp_tools_by_connection.items():
        if any(tool_meta["name"] == tool_name for tool_meta in tools_metadata):
            mcp_connection_name = conn_name
            break

    if not mcp_connection_name:
        error_msg = f"Tool '{tool_name}' not found in any active MCP connection."
        print(error_msg)
        current_step.output = json.dumps({"error": error_msg})
        current_step.is_error = True
        return json.dumps({"error": error_msg})

    mcp_session_tuple = cl.context.session.mcp_sessions.get(mcp_connection_name)
    if not mcp_session_tuple:
        error_msg = f"Active MCP session for connection '{mcp_connection_name}' not found."
        print(error_msg)
        current_step.output = json.dumps({"error": error_msg})
        current_step.is_error = True
        return json.dumps({"error": error_msg})

    mcp_session: ClientSession = mcp_session_tuple[0] # Get the session object

    # --- Execute the tool call via MCP ---
    try:
        print(f"Calling MCP tool '{tool_name}' via session for '{mcp_connection_name}'...")
        result = await mcp_session.call_tool(tool_name, arguments=tool_input)
        print(f"MCP tool '{tool_name}' returned successfully.")

        # Store result nicely formatted in the step output for UI
        if isinstance(result, (dict, list)):
           current_step.output = json.dumps(result, indent=2)
        else:
           current_step.output = str(result)

        # Return the result stringified for the OpenAI tool message content
        return str(result)

    except Exception as e:
        error_msg = f"Error executing MCP tool '{tool_name}': {e}"
        print(error_msg)
        current_step.output = json.dumps({"error": error_msg})
        current_step.is_error = True
        # Return error details stringified for the LLM
        return json.dumps({"error": error_msg})

def format_mcp_tools_for_openai(mcp_tools_by_connection):
    """
    Converts stored MCP tool metadata into the OpenAI API 'tools' format.
    """
    openai_tools = []
    # Combine tools from all active connections
    all_mcp_tools = flatten(list(mcp_tools_by_connection.values()))

    for tool_meta in all_mcp_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool_meta["name"],
                "description": tool_meta["description"],
                "parameters": tool_meta["input_schema"] # Use the JSON schema directly
            }
        })
    return openai_tools

async def call_gemini(chat_messages):
    """
    Calls the Gemini model via the OpenAI SDK, handles streaming, and tool calls.
    Uses a non-streaming call at the end to reliably get tool call details.
    """
    # We'll create the message object but not send it immediately
    # We'll only send it if we actually receive content
    msg = cl.Message(content="")
    message_sent = False

    mcp_tools_by_connection = cl.user_session.get("mcp_tools", {})
    tools_for_openai = format_mcp_tools_for_openai(mcp_tools_by_connection)

    print("-" * 50)
    print(f"Calling Gemini ({MODEL_NAME}) with {len(chat_messages)} messages.")
    if tools_for_openai:
        print(f"Providing {len(tools_for_openai)} tools.")
    else:
        print("No MCP tools available.")
    print("-" * 50)

    try:
        # Prepare common arguments for API calls
        api_args = {
            "model": MODEL_NAME,
            "messages": chat_messages,
            "temperature": 0.5,
        }
        if tools_for_openai:
            api_args["tools"] = tools_for_openai
            api_args["tool_choice"] = "auto"

        # --- Streaming call for text response ---
        print("Starting streaming call...")
        stream_resp = await client.chat.completions.create(**{**api_args, "stream": True})

        async for chunk in stream_resp:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                # Only send the message once we know there's content
                if not message_sent:
                    await msg.send()
                    message_sent = True
                await msg.stream_token(delta.content)

        # Only update the message if we actually sent it
        if message_sent:
            await msg.update()  # Finalize the streamed message in UI
            print("Streaming finished.")
        else:
            print("No content to stream, skipping message creation.")

        # --- Non-streaming call to reliably get final message object (with tool calls) ---
        # This avoids complex stream aggregation logic for tool calls.
        print("Making non-streaming call to retrieve final message with tool calls...")
        final_response = await client.chat.completions.create(**{**api_args, "stream": False})
        assistant_message = final_response.choices[0].message
        print(f"Retrieved final assistant message.")
        # print(f"Final Assistant Message Content: {assistant_message}") # Optional: Debug log

        return assistant_message # Return openai.types.chat.ChatCompletionMessage

    except Exception as e:
        error_message = f"Error calling Gemini API: {e}"
        print(error_message)
        # Only send an error message if we haven't already sent a message
        if not message_sent:
            await cl.ErrorMessage(error_message).send()
        return None # Indicate failure

@cl.on_chat_start
async def start_chat():
    """Initializes chat history and MCP tool storage on new chat session."""
    system_prompt = get_system_prompt() 
    cl.user_session.set("chat_messages", [{"role": "system", "content": system_prompt}])
    cl.user_session.set("mcp_tools", {})  # Initialize empty dict for MCP tools
    print("Chat started. Initialized history and MCP tools storage.")

@cl.on_message
async def on_message(message: cl.Message):
    """
    Handles incoming user messages, orchestrates LLM calls and tool execution loop.
    """
    chat_messages = cl.user_session.get("chat_messages")
    chat_messages.append({"role": "user", "content": message.content})

    # Loop to allow for potential sequences of LLM response -> tool call -> tool result -> LLM response
    while True:
        assistant_response_message = await call_gemini(chat_messages)

        if not assistant_response_message:
            # Error handled within call_gemini, stop processing this message
            await cl.ErrorMessage("Assistant failed to generate a response.").send()
            # Optionally remove the last user message? Depends on desired error recovery.
            # chat_messages.pop()
            return

        # Append assistant's response (might include tool_calls) to history
        # Use .model_dump() for serialization needed by user_session
        chat_messages.append(assistant_response_message.model_dump(exclude_unset=True))

        # --- Check for Tool Calls ---
        if not assistant_response_message.tool_calls:
            # No tool calls requested, conversation turn is complete.
            print("Assistant provided final response (no tool calls).")
            break # Exit the loop

        # --- Execute Tool Calls ---
        print(f"Assistant requested {len(assistant_response_message.tool_calls)} tool call(s). Executing...")
        tool_messages_for_llm = []

        for tool_call in assistant_response_message.tool_calls:
            if tool_call.type == "function":
                # Execute the tool call using the decorated step function
                tool_result_content = await call_mcp_tool(tool_call) # Handles UI step

                # Prepare the result message for the next LLM call
                tool_messages_for_llm.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id, # Link result to the specific call
                    "content": tool_result_content, # Stringified result from call_mcp_tool
                })
            else:
                print(f"Warning: Received unsupported tool call type: {tool_call.type}")
                # Optionally add an error message back to the LLM?
                tool_messages_for_llm.append({
                     "role": "tool",
                     "tool_call_id": tool_call.id,
                     "content": json.dumps({"error": f"Unsupported tool type: {tool_call.type}"}),
                 })


        # Append all tool results to the chat history
        chat_messages.extend(tool_messages_for_llm)
        print("Appended tool results to history. Continuing conversation...")
        # The loop will now call call_gemini again with the updated history

    # --- End of Conversation Turn ---
    # Update the session with the final chat history after the loop completes
    cl.user_session.set("chat_messages", chat_messages)
    print("Conversation turn complete.")