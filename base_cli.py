import re
from typing import Any, List, Tuple, cast
import xml.etree.ElementTree as ET
from openai import OpenAI
from pydantic import BaseModel
from abc import ABC, abstractmethod


class Tool(BaseModel, ABC):
    dependencies: List["Tool"]
    _enabled: bool = True
    stop_token: str
    stopping: bool = True
        
    @property
    def status_prompt(self) -> str:
        return ""
    
    @property
    def system_description(self) -> str:
        return ""
    
    @property
    def enabled(self) -> bool:
        """Tool is enabled if all its dependencies are enabled"""
        if not self.dependencies:
            return self._enabled
        return self._enabled and all(dep.enabled for dep in self.dependencies)

    @abstractmethod
    def execute(self, data: dict) -> str:
        pass


class TodoTool(Tool):
    stop_token: str = "</todo>"
    stopping: bool = False  # Non-stopping tool
    todos: List[str] = []

    @property
    def system_description(self) -> str:
        return """
        Use this to manage your task list.        
            Add tasks: <todo>
                <add>task description</add>
                <add>task description 2</add>
                ...
                </todo>
            Remove tasks: <todo>
                <remove>old task description</remove>
                <remove>old task description 2</remove>
                ...
                </todo>
            You may use multiple adds and removes in one request!
        """
    
    def execute(self, data: dict) -> str:
        added = data.get('add', [])
        removed = data.get('remove', [])
        
        for item in added:
            self.todos.append(item)
        
        for item in removed:
            self.todos.remove(item)
            
        return f"Added {len(added)}, removed {len(removed)} todos"
    
    @property
    def status_prompt(self) -> str:
        if not self.todos:
            return "Todo List: (empty)"
        
        status = "Todo List:\n"
        for i, todo in enumerate(self.todos, 1):
            status += f"  {i}. {todo}\n"
        status += "Please work to complete the first item."
        return status
    
    
    
class Jeeves:
    def __init__(self, client: OpenAI, prime_directive: str, tools: List[Tool],
                 model: str = "gpt-4", extra_body: dict = {}, on_chunk=None):
        self.client = client
        self.tools: List[Tool] = tools
        self.prime_directive = prime_directive
        self.model = model
        self.extra_body = extra_body
        self.on_chunk = on_chunk
        self.system_prompt = ""
        self.recent_actions: List[str] = []
        self.last_response: str = ""
        self.pending_errors: List[str] = []
        self.executed_tool_calls: set = set()

        self.refresh_system_prompt()

        self.think_pattern = re.compile(r"<think>[\s\S]*?</think>")
    
    def refresh_system_prompt(self) -> None:
        self.system_prompt = f"""
            You are a helpful assistant with this prime directive:
                {self.prime_directive}

            To accomplish your directive, you will be given the following tools:
                {self.get_tools()}

            IMPORTANT: Always explain your reasoning and thought process before using tools.
            Describe what you're doing and why. Use tools to accomplish tasks, but provide
            context and explanations around your actions.
            
            When discussing tools in your explanations, refer to them by name (like "read_file tool")
            rather than showing their XML format. Only use the actual XML format when you're
            ready to execute the tool.
            
            Follow tool formats strictly when using them. If you do not have a todo list, create one first thing.
            Ask for help! Learn how cli tools work by using their help commands when needed.
            When asked to create something:
            - always actually create it, write to files, etc.
            - always test your code.
            ALWAYS
            """
    def respond_once(self):
        self.refresh_system_prompt()
        # Clear executed tool calls for new response
        self.executed_tool_calls.clear()
        recent_actions_text = ""
        if self.recent_actions:
            recent_actions_text = f"""
        Recent Actions:
        {chr(10).join(self.recent_actions[-5:])}
        """
        
        prompt = f"""
        {recent_actions_text}
        Live Information:
        {self.get_tool_status()}

        Prime Directive:
        {self.prime_directive}

        Perform one thing towards your prime directive.
        """
        
        # Build messages: last assistant response, then any pending tool errors, then user prompt
        messages: List[dict] = []
        if self.last_response:
            messages.append({"role": "assistant", "content": self.last_response})
        if self.pending_errors:
            messages.append({"role": "assistant", "content": "Tool errors since last step:\n" + "\n".join(self.pending_errors)})
            self.pending_errors.clear()
        messages.append({"role": "user", "content": prompt})
        
        response = self.stream(messages)
        self.last_response = response
        
        
    def stream(self, messages: List[dict]) -> str:
        stop_tokens = [tool.stop_token for tool in self.tools if tool.enabled]
        
        # Debug info (can be removed later)
        # print(f"\n[DEBUG] Sending to API: {messages[-1]['content'][:200]}...")
        # print(f"[DEBUG] Stop tokens: {stop_tokens}")
        
        content = self._stream_content(messages, stop_tokens)
        self._execute_tools(content)
        return content

    def stream_with_xml(self, messages: List[dict]) -> Tuple[str, ET.Element]:
        stop_tokens = [tool.stop_token for tool in self.tools if tool.enabled]
        content = self._stream_content(messages, stop_tokens)
        return content, self._parse_xml(content)
    
    def get_tools(self) -> str:
        return "\n".join([tool.system_description for tool in self.tools if tool.enabled])
    
    def get_tool_status(self) -> str:
        return "\n".join([tool.status_prompt for tool in self.tools])
    
    def _stream_content(self, messages: List[dict], stop_tokens: List[str]) -> str:
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": self.system_prompt}] + cast(Any, messages),
                stream=True,
                extra_body=self.extra_body,
            )
            content = ""
            for chunk in stream:
                piece = self._extract_content(chunk)
                if not piece:
                    continue

                # Handle providers that stream cumulative content instead of deltas
                if content and piece.startswith(content):
                    new_text = piece[len(content):]
                    content = piece
                else:
                    new_text = piece
                    content += piece

                if self.on_chunk and new_text:
                    self.on_chunk(new_text)

                if self._should_stop(content, stop_tokens):
                    print(f"\n[DEBUG] Stopping due to tool detection")
                    stream.close()  # type: ignore[attr-defined]
                    break
            
            print(f"\n[DEBUG] Stream ended naturally, content length: {len(content)}")
            return content
        except Exception as e:
            error_msg = f"API Error: {e}"
            print(f"\n{error_msg}")
            self.recent_actions.append(error_msg)
            self.pending_errors.append(error_msg)
            return f"Error: {error_msg}"
    

    def _extract_content(self, chunk: Any) -> str:
        content = chunk.choices[0].delta.content
        return content if content is not None else ""

    def _should_stop(self, content: str, stop_tokens: List[str]) -> bool:
        # Remove <think> blocks first
        clean_content = self.think_pattern.sub("", content).lower()

        # Check if any complete tool tag exists
        for tool in self.tools:
            if not tool.enabled or not tool.stopping:
                continue
            tag_name = tool.stop_token[2:-1].lower()  # Extract tag name and lowercase
            if f"<{tag_name}>" in clean_content and f"</{tag_name}>" in clean_content:
                return True
        return False

    def _execute_tools(self, content: str):
        try:
            xml_root = self._parse_xml(content)
            for tool in self.tools:
                if not tool.enabled:
                    continue

                tag_name = tool.stop_token[2:-1].lower()
                elements = [el for el in xml_root.iter() if el.tag.lower() == tag_name]

                for element in elements:
                    data: dict[str, Any] = {}
                    try:
                        for child in element:
                            if child.tag in data:
                                if not isinstance(data[child.tag], list):
                                    data[child.tag] = [data[child.tag]]
                                data[child.tag].append(child.text)
                            else:
                                data[child.tag] = child.text

                        # Create unique ID for this tool call to avoid re-execution
                        tool_call_id = f"{tool.__class__.__name__}:{hash(str(data))}"
                        if tool_call_id in self.executed_tool_calls:
                            continue  # Skip already executed tool calls

                        result = tool.execute(data)
                        self.executed_tool_calls.add(tool_call_id)

                        if result:
                            self.recent_actions.append(f"{tool.__class__.__name__}: {result}")
                    except Exception as e:
                        err = f"Error executing tool {tool.__class__.__name__} with data {data}: {e}"
                        self.recent_actions.append(err)
                        self.pending_errors.append(err)
                        print(err)
        except Exception as e:
            err = f"Error parsing XML content: {e}"
            self.recent_actions.append(err)
            self.pending_errors.append(err)
            print(err)
            # Also print the problematic content for debugging
            print(f"Problematic content: {repr(content[:500])}")  # First 500 chars

    def _parse_xml(self, content: str) -> ET.Element:
        clean_content = self.think_pattern.sub("", content)
        try:
            return ET.fromstring(f"<root>{clean_content}</root>")
        except ET.ParseError:
            # Second attempt: escape inner text of known payload tags to avoid XML breakage
            sanitized = self._escape_payload_tag_text(clean_content)
            try:
                return ET.fromstring(f"<root>{sanitized}</root>")
            except ET.ParseError as e2:
                # Last resort: return empty root but keep going
                print(f"Warning: Could not parse XML content even after sanitization. Using empty root. Error: {e2}")
                return ET.fromstring("<root></root>")

    def _escape_payload_tag_text(self, src: str) -> str:

        """Wrap payload tag content in CDATA to prevent XML parsing issues."""
        payload_tags = ["content", "command", "query"]
        
        for tag in payload_tags:
            pattern = re.compile(rf"<{tag}>([\s\S]*?)</{tag}>", re.IGNORECASE)
            def repl(m, _tag=tag):
                inner = m.group(1)
                # Skip if already has CDATA
                if "<![CDATA[" in inner:
                    return m.group(0)
                return f"<{_tag}><![CDATA[{inner}]]></{_tag}>"
            src = pattern.sub(repl, src)
        return src
