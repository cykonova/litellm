"""
WebSocket handler for general client access to LiteLLM
Provides persistent bidirectional communication for chat completions
"""

import asyncio
import json
import traceback
import uuid
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect
from litellm import acompletion
from litellm.proxy._types import ProxyException
from litellm.proxy.utils import verbose_proxy_logger


class WebSocketConnectionManager:
    """Manages WebSocket connections and message routing"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept and store a new WebSocket connection"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        verbose_proxy_logger.info(f"WebSocket client {client_id} connected")
        
    def disconnect(self, client_id: str):
        """Remove a WebSocket connection"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            verbose_proxy_logger.info(f"WebSocket client {client_id} disconnected")
            
    async def send_message(self, client_id: str, message: dict):
        """Send a message to a specific client"""
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            await websocket.send_json(message)
            
    async def send_error(self, client_id: str, error: str, request_id: Optional[str] = None):
        """Send an error message to a client"""
        error_message = {
            "type": "error",
            "error": error,
            "request_id": request_id
        }
        await self.send_message(client_id, error_message)


class WebSocketChatHandler:
    """Handles chat completion requests over WebSocket"""
    
    def __init__(self, manager: WebSocketConnectionManager):
        self.manager = manager
        
    async def handle_chat_completion(
        self,
        client_id: str,
        message: dict,
        user_api_key_dict: dict,
        llm_router: Any,
        proxy_config: Any
    ):
        """Process a chat completion request"""
        request_id = message.get("request_id", str(uuid.uuid4()))
        
        try:
            # Extract parameters from message
            model = message.get("model")
            messages = message.get("messages", [])
            stream = message.get("stream", True)
            temperature = message.get("temperature")
            max_tokens = message.get("max_tokens")
            
            if not model:
                await self.manager.send_error(client_id, "Model is required", request_id)
                return
                
            if not messages:
                await self.manager.send_error(client_id, "Messages are required", request_id)
                return
            
            # Prepare completion parameters
            completion_params = {
                "model": model,
                "messages": messages,
                "stream": stream,
                "user": user_api_key_dict.get("user_id"),
                "api_key": user_api_key_dict.get("api_key"),
            }
            
            if temperature is not None:
                completion_params["temperature"] = temperature
            if max_tokens is not None:
                completion_params["max_tokens"] = max_tokens
                
            # Add any additional parameters from the message
            for key in ["top_p", "n", "stop", "presence_penalty", "frequency_penalty", "logit_bias"]:
                if key in message:
                    completion_params[key] = message[key]
            
            if stream:
                # Handle streaming response
                response = await acompletion(**completion_params, router=llm_router)
                
                async for chunk in response:
                    chunk_dict = chunk.model_dump() if hasattr(chunk, 'model_dump') else chunk
                    await self.manager.send_message(client_id, {
                        "type": "stream_chunk",
                        "request_id": request_id,
                        "data": chunk_dict
                    })
                    
                # Send completion signal
                await self.manager.send_message(client_id, {
                    "type": "stream_complete",
                    "request_id": request_id
                })
            else:
                # Handle non-streaming response
                response = await acompletion(**completion_params, router=llm_router)
                response_dict = response.model_dump() if hasattr(response, 'model_dump') else response
                
                await self.manager.send_message(client_id, {
                    "type": "completion",
                    "request_id": request_id,
                    "data": response_dict
                })
                
        except ProxyException as e:
            await self.manager.send_error(client_id, str(e), request_id)
        except Exception as e:
            verbose_proxy_logger.exception(f"Error in WebSocket chat completion: {str(e)}")
            await self.manager.send_error(client_id, f"Internal error: {str(e)}", request_id)


async def handle_websocket_client(
    websocket: WebSocket,
    user_api_key_dict: dict,
    llm_router: Any,
    proxy_config: Any
):
    """Main handler for WebSocket client connections"""
    client_id = str(uuid.uuid4())
    manager = WebSocketConnectionManager()
    chat_handler = WebSocketChatHandler(manager)
    
    await manager.connect(websocket, client_id)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await manager.send_error(client_id, "Invalid JSON format")
                continue
                
            message_type = message.get("type")
            
            if message_type == "chat_completion":
                # Handle chat completion request
                await chat_handler.handle_chat_completion(
                    client_id,
                    message,
                    user_api_key_dict,
                    llm_router,
                    proxy_config
                )
            elif message_type == "ping":
                # Respond to ping with pong
                await manager.send_message(client_id, {"type": "pong"})
            else:
                await manager.send_error(client_id, f"Unknown message type: {message_type}")
                
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        verbose_proxy_logger.exception(f"WebSocket error: {str(e)}")
        manager.disconnect(client_id)