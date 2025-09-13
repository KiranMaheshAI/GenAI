import os
from typing import TypedDict, List, Union
from langchain_core.messages import HumanMessage, AIMessage
from langchain.openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from dotenv import load_dotenv

load_dotenv()

class AgentState(TypedDict):
    messages: List[Union[HumanMessage, AIMessage]]

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

def process(state: AgentState) -> AgentState:
    """This node will solve the request you give it."""
    response = llm.invoke(state["messages"])
    state["messages"].append(AIMessage(content=response.content))
    print(f"AI: {response.content}")
    print("CURRENT STATE: ", state["messages"])
    return state

graph = StateGraph(AgentState)
graph.add_node("process", process)
graph.add_edge(START, "process")
graph.add_edge("process", END)
app = graph.compile()

conversation_history = []

user_input = input("You: ")
while user_input != "exit":
    conversation_history.append(HumanMessage(content=user_input))
    result = app.invoke({"messages": conversation_history})
    conversation_history = result["messages"]
    user_input = input("You: ")

with open("logging.txt", "w") as file:
    file.write(" Your Conversation history:\n")
    for messages in conversation_history:
        if isinstance(messages, HumanMessage):
            file.write(f"User: {messages.content}\n")
        elif isinstance(messages, AIMessage):
            file.write(f"AI: {messages.content}\n")
    file.write("End of conversation")

print("Conversation logged to logging.txt")
