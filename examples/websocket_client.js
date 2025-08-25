/**
 * Example WebSocket client for LiteLLM chat completions (JavaScript/Node.js)
 * 
 * This demonstrates how to use the WebSocket endpoint from JavaScript/TypeScript
 * for persistent, bidirectional communication with LiteLLM.
 */

class LiteLLMWebSocketClient {
    constructor(url, apiKey = null) {
        this.url = url;
        this.apiKey = apiKey;
        this.ws = null;
        this.messageHandlers = new Map();
    }

    /**
     * Connect to the WebSocket server
     */
    connect() {
        return new Promise((resolve, reject) => {
            // For Node.js, use 'ws' library
            // For browser, use native WebSocket
            if (typeof window === 'undefined') {
                // Node.js environment
                const WebSocket = require('ws');
                const headers = {};
                if (this.apiKey) {
                    headers['Authorization'] = `Bearer ${this.apiKey}`;
                }
                this.ws = new WebSocket(this.url, { headers });
            } else {
                // Browser environment
                this.ws = new WebSocket(this.url);
            }

            this.ws.onopen = () => {
                console.log(`Connected to ${this.url}`);
                resolve();
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                reject(error);
            };

            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            };

            this.ws.onclose = () => {
                console.log('Disconnected from server');
            };
        });
    }

    /**
     * Disconnect from the WebSocket server
     */
    disconnect() {
        if (this.ws) {
            this.ws.close();
        }
    }

    /**
     * Send a chat completion request
     */
    async sendChatCompletion(options) {
        const {
            model,
            messages,
            stream = true,
            temperature = null,
            maxTokens = null,
            onChunk = null,
            ...additionalParams
        } = options;

        const requestId = this.generateUUID();

        // Build request message
        const request = {
            type: 'chat_completion',
            request_id: requestId,
            model,
            messages,
            stream,
            ...additionalParams
        };

        if (temperature !== null) {
            request.temperature = temperature;
        }
        if (maxTokens !== null) {
            request.max_tokens = maxTokens;
        }

        // Set up response handler
        return new Promise((resolve, reject) => {
            let fullResponse = '';

            this.messageHandlers.set(requestId, (data) => {
                if (data.type === 'error') {
                    reject(new Error(data.error));
                    this.messageHandlers.delete(requestId);
                } else if (data.type === 'stream_chunk' && stream) {
                    const chunk = data.data;
                    if (chunk.choices && chunk.choices[0]?.delta?.content) {
                        const content = chunk.choices[0].delta.content;
                        fullResponse += content;
                        if (onChunk) {
                            onChunk(content);
                        }
                    }
                } else if (data.type === 'stream_complete' && stream) {
                    resolve(fullResponse);
                    this.messageHandlers.delete(requestId);
                } else if (data.type === 'completion' && !stream) {
                    const completion = data.data;
                    if (completion.choices && completion.choices[0]?.message?.content) {
                        resolve(completion.choices[0].message.content);
                    } else {
                        resolve(completion);
                    }
                    this.messageHandlers.delete(requestId);
                }
            });

            // Send request
            this.ws.send(JSON.stringify(request));
            console.log(`Sent request ${requestId}`);
        });
    }

    /**
     * Send a ping message to keep connection alive
     */
    async ping() {
        return new Promise((resolve, reject) => {
            const pingId = this.generateUUID();
            
            this.messageHandlers.set(pingId, (data) => {
                if (data.type === 'pong') {
                    console.log('Received pong');
                    resolve();
                    this.messageHandlers.delete(pingId);
                }
            });

            this.ws.send(JSON.stringify({ type: 'ping', request_id: pingId }));
            
            // Timeout after 5 seconds
            setTimeout(() => {
                if (this.messageHandlers.has(pingId)) {
                    this.messageHandlers.delete(pingId);
                    reject(new Error('Ping timeout'));
                }
            }, 5000);
        });
    }

    /**
     * Handle incoming messages
     */
    handleMessage(data) {
        const requestId = data.request_id;
        if (requestId && this.messageHandlers.has(requestId)) {
            this.messageHandlers.get(requestId)(data);
        }
    }

    /**
     * Generate a UUID
     */
    generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }
}

// Example usage
async function main() {
    // Configure your LiteLLM server URL and API key
    const URL = 'ws://localhost:4000/v1/chat/completions/ws';
    const API_KEY = 'your-api-key-here'; // Optional, if authentication is enabled

    // Create client
    const client = new LiteLLMWebSocketClient(URL, API_KEY);

    try {
        // Connect to server
        await client.connect();

        // Example 1: Streaming chat completion with chunk handler
        console.log('\n=== Streaming Chat Completion ===');
        const response1 = await client.sendChatCompletion({
            model: 'gpt-3.5-turbo',
            messages: [
                { role: 'system', content: 'You are a helpful assistant.' },
                { role: 'user', content: 'Write a haiku about WebSockets' }
            ],
            stream: true,
            temperature: 0.7,
            onChunk: (chunk) => {
                process.stdout.write(chunk); // Print chunks as they arrive
            }
        });
        console.log('\n[Stream complete]');

        // Example 2: Non-streaming chat completion
        console.log('\n=== Non-Streaming Chat Completion ===');
        const response2 = await client.sendChatCompletion({
            model: 'gpt-3.5-turbo',
            messages: [
                { role: 'user', content: 'What is 2+2?' }
            ],
            stream: false
        });
        console.log('Response:', response2);

        // Example 3: Multiple requests on same connection
        console.log('\n=== Multiple Requests ===');
        for (let i = 0; i < 3; i++) {
            console.log(`\nRequest ${i + 1}:`);
            const response = await client.sendChatCompletion({
                model: 'gpt-3.5-turbo',
                messages: [
                    { role: 'user', content: 'Generate a random number between 1 and 100' }
                ],
                stream: false
            });
            console.log('Response:', response);
        }

        // Keep connection alive with ping
        await client.ping();

    } catch (error) {
        console.error('Error:', error);
    } finally {
        // Disconnect
        client.disconnect();
    }
}

// Run the example
if (require.main === module) {
    main().catch(console.error);
}

// Export for use as a module
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LiteLLMWebSocketClient;
}