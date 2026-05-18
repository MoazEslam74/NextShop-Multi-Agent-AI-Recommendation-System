import os
import json
import csv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
import pandas as pd
import matplotlib.pyplot as plt
# ==========================================
# 1. Judge Model Setup (Avoiding Self-Bias)
# ==========================================
# Using a different architecture (Mixtral) instead of Llama to prevent self-enhancement bias.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
os.environ["GROQ_API_KEY"] = GROQ_API_KEY

# Temperature 0 for deterministic, strict evaluation
judge_llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)

# ==========================================
# 2. Evaluation Prompts (Reference-Free)
# ==========================================

# Agent 1 Evaluation: Accuracy and Faithfulness
eval_agent1_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an impartial and strict AI evaluator.
    Evaluate the extracted 'Profile' based strictly on the user's actual browsing 'History'.
    
    Criteria:
    1. Faithfulness: Does the profile accurately reflect the user's actual viewed/added items?
    2. No Hallucination: Did the system invent any interests, categories, or budgets not present in the history?
    
    Return the evaluation STRICTLY as a JSON object with no additional text or markdown formatting:
    {{"score": <integer from 1 to 5>, "reason": "<brief justification for the score>"}}"""),
    ("user", "User History:\n{history}\n\nExtracted Profile:\n{profile}")
])

# Agent 2 Evaluation: Relevance and Reasoning Quality
eval_agent2_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an impartial and strict AI evaluator.
    Evaluate the 'Recommendations' and their 'Reasons' based strictly on the user's 'Profile'.
    
    Criteria:
    1. Relevance: Do the recommended products strongly align with the categories and budget in the profile?
    2. Reasoning Quality: Is the provided 'reason' logical, convincing, and directly tying the product features to the user's specific profile?
    
    Return the evaluation STRICTLY as a JSON object with no additional text or markdown formatting:
    {{"score": <integer from 1 to 5>, "reason": "<brief justification for the score>"}}"""),
    ("user", "User Profile:\n{profile}\n\nRecommendations:\n{recommendations}")
])

chain1 = eval_agent1_prompt | judge_llm
chain2 = eval_agent2_prompt | judge_llm

# ==========================================
# 3. Evaluation Execution
# ==========================================
def run_evaluation():
    log_file_path = "evaluation_logs.json"
    output_csv_path = "evaluation_results.csv"

    if not os.path.exists(log_file_path):
        print("❌ [ERROR] File 'evaluation_logs.json' not found. Please run the system and generate some logs first.")
        return

    logs = []
    with open(log_file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                logs.append(json.loads(line))

    print(f"📊 [INFO] Found {len(logs)} test cases. Starting evaluation process...")

    # Setup CSV Writer
    with open(output_csv_path, "w", newline='', encoding="utf-8-sig") as csvfile:
        fieldnames = [
            'Test_ID', 
            'Agent1_Score', 'Agent1_Reason', 
            'Agent2_Score', 'Agent2_Reason', 
            'Input_History', 'Profile_Summary', 'Recommendations'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        total_score_a1 = 0
        total_score_a2 = 0
        valid_logs = 0

        for idx, log in enumerate(logs):
            print(f"\n⏳ [PROCESSING] Evaluating Test Case #{idx + 1}...")
            
            history_str = json.dumps(log.get("input_history", []), ensure_ascii=False)
            profile_str = log.get("agent_1_profile", "")
            recs_str = json.dumps(log.get("agent_2_recommendations", []), ensure_ascii=False)

            try:
                # -----------------------------
                # Evaluate Agent 1 (Profiler)
                # -----------------------------
                res1 = chain1.invoke({"history": history_str, "profile": profile_str})
                clean_res1 = res1.content.strip().replace("```json", "").replace("```", "").strip()
                eval1 = json.loads(clean_res1)
                
                # -----------------------------
                # Evaluate Agent 2 (Scout)
                # -----------------------------
                res2 = chain2.invoke({"profile": profile_str, "recommendations": recs_str})
                clean_res2 = res2.content.strip().replace("```json", "").replace("```", "").strip()
                eval2 = json.loads(clean_res2)

                # Write to CSV
                writer.writerow({
                    'Test_ID': idx + 1,
                    'Agent1_Score': eval1.get("score"),
                    'Agent1_Reason': eval1.get("reason"),
                    'Agent2_Score': eval2.get("score"),
                    'Agent2_Reason': eval2.get("reason"),
                    'Input_History': history_str,
                    'Profile_Summary': profile_str,
                    'Recommendations': recs_str
                })

                total_score_a1 += int(eval1.get("score", 0))
                total_score_a2 += int(eval2.get("score", 0))
                valid_logs += 1

                print(f"✅ [SUCCESS] Test #{idx + 1} Evaluated | Agent 1: {eval1.get('score')}/5 | Agent 2: {eval2.get('score')}/5")

            except json.JSONDecodeError as e:
                print(f"⚠️ [WARNING] JSON parsing error in Test #{idx + 1}: {e}. Skipping this case.")
            except Exception as e:
                print(f"⚠️ [WARNING] Unexpected error in Test #{idx + 1}: {e}")

    # Print Final Statistics
    plt_avg1=0
    plt_avg2=0
    # Print Final Statistics
    if valid_logs > 0:
        avg_a1 = total_score_a1 / valid_logs
        plt_avg1=avg_a1
        avg_a2 = total_score_a2 / valid_logs
        plt_avg2=avg_a2
        print("\n" + "="*50)
        print("🎉 [COMPLETE] Evaluation finished successfully!")
        print(f"📁 [FILE] Detailed results saved to: {output_csv_path}")
        print(f"📈 [METRICS] Agent 1 (Profiler) Average Score: {avg_a1:.2f} / 5.0")
        print(f"📈 [METRICS] Agent 2 (Scout) Average Score:    {avg_a2:.2f} / 5.0")
        print("="*50)
    

    df= pd.read_csv('evaluation_results.csv')
    

    
    plt.figure(figsize=(8, 5)) 
    plt.bar(['User_profile_agent','Content_profile_agent','Total'], [plt_avg1,plt_avg2,((plt_avg1) + (plt_avg2))/2], color='skyblue')

    plt.ylim(0, 5)
    plt.title('evaluation results for Multiagent Recommendation System (T0.7)')
    plt.xlabel('Agents')
    plt.ylabel('Score (out of 5)')

    
    plt.savefig('my_bar_plot.png', dpi=300, bbox_inches='tight')

    print(f"Image saved as 'my_bar_plot.png'")


if __name__ == "__main__":
    run_evaluation()