import os
import json
import time
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain.agents import AgentExecutor, create_tool_calling_agent

# ==========================================
# App Setup
# ==========================================
app = FastAPI(title="E-Commerce Multi-Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# LLM Setup - Replace with your key
# ==========================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
os.environ["GROQ_API_KEY"] = GROQ_API_KEY
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.5)

# ==========================================
# Pydantic Models
# ==========================================
class UserAction(BaseModel):
    action: str           # "search" | "view" | "add_to_cart" | "purchase"
    keyword: Optional[str] = None
    product_id: Optional[int] = None
    product_title: Optional[str] = None
    product_category: Optional[str] = None
    price: Optional[float] = None
    timestamp: Optional[str] = None

class RecommendationRequest(BaseModel):
    user_id: str
    history: List[UserAction]

class Product(BaseModel):
    id: int
    title: str
    price: float
    description: str
    category: str
    image: str
    rating: dict

# ==========================================
# Store API
# ==========================================
FAKE_STORE_BASE = "https://fakestoreapi.com"

def fetch_all_products() -> List[dict]:
    """Fetch all products from Fake Store API with detailed logging."""
    print("\n" + "="*50)
    print("🌐 [API FETCH] Attempting to connect to Fake Store API...")
    start_time = time.time()
    
    try:
        # Attempting to connect to the Fake Store API with a 30-second timeout
        # Pretending to be a regular Chrome browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json'
        }
        
        # Sending the headers with the request
        response = requests.get(f"{FAKE_STORE_BASE}/products", headers=headers, timeout=30)
        
        # This line will raise an error if the API returns 404 or 500 (server error)
        response.raise_for_status() 
        
        duration = time.time() - start_time
        print(f"✅ [API SUCCESS] Successfully fetched data in {duration:.2f} seconds.")
        print("="*50 + "\n")
        return response.json()
        
    except requests.exceptions.Timeout:
        duration = time.time() - start_time
        print(f"❌ [API TIMEOUT] Fake Store API did not respond after {duration:.2f} seconds!")
    except requests.exceptions.HTTPError as errh:
        print(f"❌ [API HTTP ERROR] Fake Store API returned an error: {errh}")
    except requests.exceptions.ConnectionError as errc:
        print(f"❌ [API CONNECTION ERROR] Could not connect to Fake Store API: {errc}")
    except Exception as e:
        print(f"❌ [API UNKNOWN ERROR] An unexpected error occurred: {e}")

    # If the code reaches here, it means the API failed for any of the reasons above
    print("🔄 [SYSTEM] Activating Emergency Fallback Dataset...")
    print("="*50 + "\n")
    
    # Emergency fallback data (you can use the 10 products sent above or these 3 as you like)
    return [
        {"id": 1, "title": "Fjallraven - Foldsack No. 1 Backpack", "price": 109.95, "category": "men's clothing", "description": "Perfect pack for everyday use.", "image": "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=500&q=80", "rating": {"rate": 3.9, "count": 120}},
        {"id": 2, "title": "Mens Casual Premium Slim Fit T-Shirts", "price": 22.3, "category": "men's clothing", "description": "Slim-fitting style, contrast raglan long sleeve.", "image": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=500&q=80", "rating": {"rate": 4.1, "count": 259}},
        {"id": 3, "title": "Mens Cotton Winter Jacket", "price": 55.99, "category": "men's clothing", "description": "Great outerwear jackets for Winter.", "image": "https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=500&q=80", "rating": {"rate": 4.7, "count": 500}},
    ]

@tool
def fetch_products_from_store(query: str = "") -> str:
    """
    Fetches all available products from the store (name, category, price).
    Always use this tool to search the inventory.
    """
    products = fetch_all_products()
    summary = [
        f"ID:{p['id']} | Name: {p['title']} | Category: {p['category']} | Price: ${p['price']} | Rating: {p.get('rating', {}).get('rate', 'N/A')}"
        for p in products
    ]
    return str(summary)

tools = [fetch_products_from_store]

# ==========================================
# Agent 1: User Profiler Chain
# ==========================================
profiler_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a professional e-commerce data analyst. 
    Read the user's action history and deduce their profile in 2-3 concise lines.
    
    CRITICAL WEIGHTING RULES (Intent Analysis):
    1. 'purchase' and 'add_to_cart' show STRONG intent. Give them 70% of your focus.
    2. 'view' and 'search' show WEAK intent. Give them only 30% of your focus.
    3. If a user views Category A but adds/purchases Category B, you MUST conclude that Category B is their true primary interest.
    
    Based on the above rules, deduce:
    1. What category/type of products is the user most interested in (weighted towards high-intent actions)?
    2. What is their estimated budget range (focusing primarily on added/purchased item prices)?
    3. Any specific keywords or preferences?
    
    Be specific and data-driven."""),
    ("user", "{user_history}")
])
profiler_chain = profiler_prompt | llm

# ==========================================
# Agent 2: Product Scout Agent
# ==========================================
scout_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an expert personal shopper AI. 
    Given the user analysis below, use the fetch_products_from_store tool to get all products.
    Then select the TOP 5 products that best match the user's interests and budget.
    
    Return your response as a JSON array with exactly 5 objects, each having:
    - product_id (integer, from the ID: field in the product list)
    - reason (why this matches the user)
    
    Example format:
    [
      {{"product_id": 1, "reason": "Matches interest in electronics within budget"}},
      {{"product_id": 3, "reason": "High-rated item in preferred category"}},
      {{"product_id": 7, "reason": "Frequently added to carts by similar users"}},
      {{"product_id": 2, "reason": "Contains keywords user searched for"}},
      {{"product_id": 5, "reason": "Fits budget and aligns with search history"}},
      {{"product_id": 8, "reason": "In the same category as items user added to cart"}}
    ]
    
    Return ONLY the JSON array, no extra text."""),
    ("user", "User interests analysis:\n{profile}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, scout_prompt)
scout_executor = AgentExecutor(agent=agent, tools=tools, verbose=False)

# ==========================================
# API Endpoints
# ==========================================

@app.get("/products", response_model=List[dict])
def get_products():
    """Get all products from Fake Store API."""
    products = fetch_all_products()
    return products

@app.get("/products/{category}")
def get_products_by_category(category: str):
    """Get products by category."""
    try:
        response = requests.get(f"{FAKE_STORE_BASE}/products/category/{category}", timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    all_products = fetch_all_products()
    return [p for p in all_products if p.get("category", "").lower() == category.lower()]

@app.get("/categories")
def get_categories():
    """Get all product categories."""
    try:
        response = requests.get(f"{FAKE_STORE_BASE}/products/categories", timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return ["electronics", "jewelery", "men's clothing", "women's clothing"]

@app.post("/recommend")
def get_recommendations(request: RecommendationRequest):
    """
    Main multi-agent recommendation endpoint.
    Takes user history → Profile Agent → Scout Agent → Returns top 5 products with details.
    """
    if not request.history:
        raise HTTPException(status_code=400, detail="User history is empty.")

    # Format history for the profiler
    history_json = json.dumps({
        "user_id": request.user_id,
        "history": [h.dict() for h in request.history]
    }, indent=2)

    # Agent 1: Profile user
    profile_result = profiler_chain.invoke({"user_history": history_json})
    profile_summary = profile_result.content

    # Agent 2: Scout products
    scout_result = scout_executor.invoke({"profile": profile_summary})
    raw_output = scout_result["output"]

    # Parse the JSON from scout
    try:
        # Clean up any markdown fences
        clean = raw_output.strip().replace("```json", "").replace("```", "").strip()
        recommendations = json.loads(clean)
    except Exception:
        # Fallback: return first 5 products
        all_products = fetch_all_products()
        recommendations = [
            {"product_id": p["id"], "reason": "Recommended based on your browsing history"}
            for p in all_products[:5]
        ]

    # Enrich recommendations with full product details
    all_products = fetch_all_products()
    products_map = {p["id"]: p for p in all_products}

    enriched = []
    for rec in recommendations[:5]:
        pid = rec.get("product_id")
        product = products_map.get(pid)
        if product:
            enriched.append({
                "product": product,
                "reason": rec.get("reason", "Matches your interests")
            })
    # === Evaluation logger code for later analysis ===
    log_entry = {
        "timestamp": time.time(),
        "input_history": [h.dict() for h in request.history],
        "agent_1_profile": profile_summary,
        "agent_2_recommendations": [
            {"product_name": rec.get("product", {}).get("title"), "reason": rec.get("reason")} 
            for rec in enriched
        ]
    }
    
    # Save this log entry to evaluation_logs.json
    try:
        with open("evaluation_logs.json", "a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"Error saving log: {e}")
    # ==========================================================

    
    return {
        "user_id": request.user_id,
        "profile_summary": profile_summary,
        "recommendations": enriched
    }

@app.get("/health")
def health_check():
    return {"status": "ok", "model": "llama-3.3-70b-versatile"}
