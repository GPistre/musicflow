import os
import json
from typing import Dict, List, Any, Optional

import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure OpenAI API
openai.api_key = os.getenv("OPENAI_API_KEY")

class LLMGenerator:
    """Class to handle interactions with the LLM for MIDI generation"""
    
    def __init__(self, model="gpt-4o"):
        self.model = model
        self.conversation_history = []
    
    def add_system_message(self, content: str):
        """Add a system message to the conversation history"""
        self.conversation_history.append({"role": "system", "content": content})
    
    def add_user_message(self, content: str):
        """Add a user message to the conversation history"""
        self.conversation_history.append({"role": "user", "content": content})
    
    def add_assistant_message(self, content: str):
        """Add an assistant message to the conversation history"""
        self.conversation_history.append({"role": "assistant", "content": content})
    
    def generate_response(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Generate a response from the LLM"""
        # Reset conversation if needed
        if not self.conversation_history:
            if system_prompt:
                self.add_system_message(system_prompt)
        
        # Add the user prompt
        self.add_user_message(prompt)
        
        try:
            response = openai.chat.completions.create(
                model=self.model,
                messages=self.conversation_history,
                response_format={"type": "json_object"},
                temperature=0.8,  # Slightly more creative for music generation
            )
            
            # Parse the JSON response
            content = response.choices[0].message.content
            midi_data = json.loads(content)
            
            # Add the assistant's response to the conversation history
            self.add_assistant_message(content)
            
            return midi_data
        except Exception as e:
            print(f"Error generating LLM response: {e}")
            return {"error": str(e)}
