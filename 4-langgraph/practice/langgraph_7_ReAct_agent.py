from typing import TypedDict, Sequence, Annotated
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain.openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

load_dotenv()

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

@tool
def add(a: int, b:int):
    """This is an addition function that add 2 numbers together"""
    return a+b

@tool
def multiply(a: int, b:int):
    """This is a multiplication function that multiply 2 numbers together"""
    return a*b

@tool
def subtract(a: int, b: int):
    """This is a subtraction function that subtracts 2 numbers"""
    return a-b

tools = [add, multiply, subtract]
llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
model = llm.bind_tools(tools)

def model_call(state: AgentState) -> AgentState:
    system_prompt = SystemMessage(content="You are my AI assistant, please answer my query to the best of your ability.")
    response = model.invoke([system_prompt] + state["messages"] )
    return {"messages": [response]}

def should_continue(state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    if not last_message.tool_calls:
        return "end"
    else:
        return "continue"
    
graph = StateGraph(AgentState)
graph.add_node("model_call", model_call)
tool_node = ToolNode(tools=tools)
graph.add_node("tool_node", tool_node)
graph.add_conditional_edges(
    "model_call",
    should_continue,
    {
        "continue": "tool_node",
        "end": END
    },
)

graph.add_edge("tool_node", "model_call")
graph.add_edge(START, "model_call")
app = graph.compile()

def print_stream(stream):
    for s in stream:
        message = s["messages"][-1]
        if isinstance(message, tuple):
            print(message)
        else:
            message.pretty_print()

inputs = {"messages": [HumanMessage(content="What is 25 multiplied by 4, then add 10 and subtract 15?")]}
print_stream(app.stream_invoke(inputs))
