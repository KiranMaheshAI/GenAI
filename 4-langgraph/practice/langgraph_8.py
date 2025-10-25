from typing import Annotated, Sequence, TypedDict
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

load_dotenv()

document_content = ""

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

@tool
def update(content: str) -> str:
    """"Update the document with the provided content."""
    global document_content
    document_content = content
    return f"Doccument has been updated successfully! the current content is : \n {document_content}"

@tool
def save(filename: str) -> str:
    """Save the current document to the text file and finsih the process.
    Args:
        filename (str): The name of the file to save the document to.
    """
    global document_content
    if not filename.endswith(".txt"):
        filename += ".txt"
    try:
        with open(filename, "w") as file:
            file.write(document_content)
            print(f"Document saved successfully to {filename}")
        return f"Document saved successfully to {filename}"
    except Exception as e:
        print(f"Error saving document: {e}")
        return f"Error saving document: {e}"
    
tools = [update, save]
model = ChatOpenAI(model="gpt-3.5-turbo", temperature=0).bind_tools(tools)

def our_agent(state: AgentState) -> AgentState:
    system_prompt = SystemMessage(content=f"""
                                  You are Drafter, a helpful writing assistant. You are going to help the user update and modify documents.
                                  - If the user wants to update or modify content, use the `update` tool with complete updated content.
                                  - If the user want to save the document, use the `save` tool with the filename.
                                  - Make sure to allways show the current document state after modifications.
                                  
                                  The Current document content is: {document_content}
                                  """)
    if not state["messages"]:
        user_input = " I'm ready to help you update a document, what would you like to create?"
        user_message = HumanMessage(content=user_input)
    else:
        user_input = input("\n What would you like to do with the document?")
        print(f"\n USER: {user_input}")
        user_message = HumanMessage(content=user_input)

    all_messages = [system_prompt]+list(state["messages"])+[user_message]

    response = model.invoke(all_messages)
    print(f"\n AI: {response.content}")
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tool_call in response.tool_calls:
            print(f"\n AI used tool: {tool_call}")


    return {"messages": list(state["messages"])+ [user_message, response]}

def should_continue(state: AgentState) -> str:
    """Determine if we should continue or end the conversation"""
    messages = state["messages"]
    if not messages:
        return "continue"
    
    for message in reversed(messages):
        if (isinstance(message, ToolMessage) and 
            "saved" in message.content.lower() and 
            "document" in message.content.lower()):
            return "end"
    return "continue"

def print_messages(messages):
    """Function I made to print the messages in readable format."""
    if not messages:
        return
    for message in messages[-3:]:
        if isinstance(message, ToolMessage):
            print(f"\n Tool Result: {message.content}")

graph = StateGraph(AgentState)
graph.add_node("our_agent", our_agent)
graph.add_node("tool_node", ToolNode(tools=tools))
graph.set_entry_point("our_agent")
graph.add_conditional_edges(
    "our_agent",
    should_continue,
    {
        "continue": "tool_node",
        "end": END
    },
)
graph.add_edge("tool_node", "our_agent")
app = graph.compile()

def run_document_agent():
    print("\n ====== DRAFTER ========")
    state = {"messages": []}
    for step in app.stream(state, stream_mode="values"):
        if "messages" in step:
            print_messages(step["messages"])
    
    print("\n ==== DRAFTER FINISHED")

if __name__ == "__main__":
    run_document_agent()
