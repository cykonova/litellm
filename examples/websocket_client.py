#!/usr/bin/env python3
"""
Example WebSocket client for LiteLLM chat completions

This demonstrates how to use the WebSocket endpoint for persistent,
bidirectional communication with LiteLLM.
"""

import asyncio
import json
import uuid
import websockets
from typing import Optional


class LiteLLMWebSocketClient:
    """WebSocket client for LiteLLM chat completions"""
    
    def __init__(self, url: str, api_key: Optional[str] = None):
        """
        Initialize WebSocket client
        
        Args:
            url: WebSocket URL (e.g., "ws://localhost:4000/v1/chat/completions/ws")
            api_key: Optional API key for authentication
        """
        self.url = url
        self.api_key = api_key
        self.websocket = None
        
    async def connect(self):
        """Connect to the WebSocket server"""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        self.websocket = await websockets.connect(self.url, extra_headers=headers)
        print(f"Connected to {self.url}")
        
    async def disconnect(self):
        """Disconnect from the WebSocket server"""
        if self.websocket:
            await self.websocket.close()
            print("Disconnected from server")
            
    async def send_chat_completion(
        self,
        model: str,
        messages: list,
        stream: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """
        Send a chat completion request
        
        Args:
            model: Model to use
            messages: List of message dicts
            stream: Whether to stream the response
            temperature: Optional temperature
            max_tokens: Optional max tokens
            **kwargs: Additional parameters
        """
        request_id = str(uuid.uuid4())
        
        # Build request message
        request = {
            "type": "chat_completion",
            "request_id": request_id,
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        if temperature is not None:
            request["temperature"] = temperature
        if max_tokens is not None:
            request["max_tokens"] = max_tokens
            
        # Add any additional parameters
        request.update(kwargs)
        
        # Send request
        await self.websocket.send(json.dumps(request))
        print(f"Sent request {request_id}")
        
        # Handle response
        if stream:
            await self._handle_streaming_response(request_id)
        else:
            await self._handle_single_response(request_id)
            
    async def _handle_streaming_response(self, request_id: str):
        """Handle a streaming response"""
        full_response = ""
        
        while True:
            response = await self.websocket.recv()
            data = json.loads(response)
            
            if data.get("type") == "error":
                print(f"Error: {data.get('error')}")
                break
            elif data.get("type") == "stream_chunk" and data.get("request_id") == request_id:
                chunk = data.get("data", {})
                # Extract content from chunk
                if "choices" in chunk and len(chunk["choices"]) > 0:
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        print(content, end="", flush=True)
                        full_response += content
            elif data.get("type") == "stream_complete" and data.get("request_id") == request_id:
                print("\n[Stream complete]")
                break
                
        return full_response
        
    async def _handle_single_response(self, request_id: str):
        """Handle a non-streaming response"""
        while True:
            response = await self.websocket.recv()
            data = json.loads(response)
            
            if data.get("type") == "error":
                print(f"Error: {data.get('error')}")
                break
            elif data.get("type") == "completion" and data.get("request_id") == request_id:
                completion = data.get("data", {})
                if "choices" in completion and len(completion["choices"]) > 0:
                    content = completion["choices"][0]["message"]["content"]
                    print(f"Response: {content}")
                    return content
                break
                
    async def send_ping(self):
        """Send a ping message to keep connection alive"""
        await self.websocket.send(json.dumps({"type": "ping"}))
        response = await self.websocket.recv()
        data = json.loads(response)
        if data.get("type") == "pong":
            print("Received pong")


async def main():
    """Example usage of the WebSocket client"""
    
    # Configure your LiteLLM server URL and API key
    URL = "ws://localhost:4000/v1/chat/completions/ws"
    API_KEY = "your-api-key-here"  # Optional, if authentication is enabled
    
    # Create client
    client = LiteLLMWebSocketClient(URL, API_KEY)
    
    try:
        # Connect to server
        await client.connect()
        
        # Example 1: Streaming chat completion
        print("\n=== Streaming Chat Completion ===")
        await client.send_chat_completion(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Write a haiku about WebSockets"}
            ],
            stream=True,
            temperature=0.7
        )
        
        # Example 2: Non-streaming chat completion
        print("\n=== Non-Streaming Chat Completion ===")
        await client.send_chat_completion(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": "What is 2+2?"}
            ],
            stream=False
        )
        
        # Example 3: Multiple requests on same connection
        print("\n=== Multiple Requests ===")
        for i in range(3):
            print(f"\nRequest {i+1}:")
            await client.send_chat_completion(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "user", "content": f"Generate a random number between 1 and 100"}
                ],
                stream=False
            )
            
        # Keep connection alive with ping
        await client.send_ping()
        
    finally:
        # Disconnect
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())