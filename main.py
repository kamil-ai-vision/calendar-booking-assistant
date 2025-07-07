from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from agent import run_agent, get_agent_executor, check_availability  # ✅ NEW

app = FastAPI()

# CORS to allow frontend (like Streamlit) to make API calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UserMessage(BaseModel):
    message: str

SANITY_TEST_MODE = False

# ✅ Global memory + agent
agent_executor = get_agent_executor()

@app.get("/")
def read_root():
    return {"message": "🧠 Calendar Assistant API is running!"}

@app.post("/agent")
def chat_with_agent(request: UserMessage):
    print(f"\n📥 Received message: {request.message}")
    try:
        if SANITY_TEST_MODE:
            print("🧪 Using tool directly (Sanity Mode)")
            return {
                "response": check_availability("2025-07-07")
            }

        # ✅ Use persistent LLM-backed agent
        reply = run_agent(request.message)
        print(f"Agent reply: {reply}")
        return {"response": reply}

    except Exception as e:
        print(f"❌ Error in /agent: {e}")
        return {"response": f"❌ Server error: {e}"}
    


# ✅ Run API: uvicorn main:app --reload
# ✅ Open Docs: http://127.0.0.1:8000/docs