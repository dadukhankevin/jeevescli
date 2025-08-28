import os
import platform
import re
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from .base_cli import Tool

# Fix tokenizer warnings
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from pysublime import Embeddings  # type: ignore[import-untyped]

@dataclass
class SearchResult:
    """Search result type"""
    path: str
    start: int
    end: int

class FindLikeTool(Tool):
    model_config = {"arbitrary_types_allowed": True}
    
    dependencies: List[Tool] = []
    stop_token: str = "</find_like>"
    folder: str = "."
    search_results: List[SearchResult] = []
    embeddings: Optional[Embeddings] = None
    stopping: bool = True
    
    def __init__(self, folder: str = ".", **kwargs):
        super().__init__(dependencies=[], stop_token="</find_like>", **kwargs)
        self.folder = folder
        self.search_results = []
        self.embeddings = Embeddings(self.folder)

    @property
    def system_description(self) -> str:
        return """
        <find_like>
            <query>pseudocode or description of what you're looking for</query>
            <query>another hypothesis about the code structure</query>
            <query>yet another search hypothesis</query>
        </find_like>
        
        Use hypothesis-based searching to find code that matches your expectations.
        Write pseudocode or describe the structure you expect to find. Examples:
        
        <find_like>
            <query>
             code snippet 1...
            </query>
            <query>
            code snippet 2...
            </query>
        </find_like>
        
        <find_like>
            <query>
            code snippet 1...
            </query>
            <query>
            code snippet 2...
            </query>
        </find_like>
        """

    @property
    def status_prompt(self) -> str:
        if not self.search_results:
            return "No search results available. Use find_like to search for code matching your hypotheses."
        
        status = f"Found Code ({len(self.search_results)} matches):\n"
        for i, result in enumerate(self.search_results[:5], 1):
            content = self._get_live_result(result)
            status += f"Match {i}: {result.path}:{result.start}-{result.end}\n"
            status += f"<section>\n{content}\n</section>\n\n"
        
        if len(self.search_results) > 5:
            status += f"... and {len(self.search_results) - 5} more matches\n"
        
        return status

    def execute(self, data: Dict[str, Any]) -> str:
        # Extract all queries from the data
        queries = data.get('query', [])
        if isinstance(queries, str):
            queries = [queries]
        
        all_results = []
        if self.embeddings is None:
            return "Embeddings not initialized. Unable to perform search."

        assert self.embeddings is not None  # for type checker
        for query in queries:
            query = query.strip()
            results = self.embeddings.search(query=query)
            all_results.extend(results)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_results = []
        for r in all_results:
            key = (r.file_path, r.start_line, r.end_line)  # type: ignore[attr-defined]
            if key not in seen:
                seen.add(key)
                unique_results.append(r)
        
        self.search_results = [
            SearchResult(path=r.file_path, start=r.start_line, end=r.end_line)  # type: ignore[attr-defined]
            for r in unique_results
        ]
        
        return f"Found {len(self.search_results)} matches"

    def _get_live_result(self, search_result: SearchResult) -> str:
        """Get live content from search result"""
        path = search_result.path
        start = search_result.start
        end = search_result.end

        path = _normalize_path(path)

        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except (OSError, IOError, FileNotFoundError, PermissionError, UnicodeDecodeError) as e:
            return f"Error reading file {path}: {e}"

        # Validate line range
        if start < 1 or end > len(lines) or start > end:
            return f"Invalid line range {start}-{end} for file {path} (file has {len(lines)} lines)"

        selected_lines = lines[start-1:end]
        numbered_lines = []

        for i, line in enumerate(selected_lines):
            line_number = start + i
            stripped_line = line[:-1] if line.endswith("\n") else line
            numbered_lines.append(f"{line_number}: {stripped_line}")

        return '\n'.join(numbered_lines)

    def get_results(self) -> List[SearchResult]:
        """Get current search results"""
        return self.search_results.copy()

    def clear_results(self) -> None:
        """Clear current search results"""
        self.search_results.clear()


class SetFileContentTool(Tool):
    dependencies: List[Tool] = []
    stop_token: str = "</set_file>"
    stopping: bool = False
    
    def __init__(self, **kwargs):
        super().__init__(stop_token="</set_file>", **kwargs)

    @property
    def system_description(self) -> str:
        return """
        <set_file>
            <name>filename</name>
            <content>
            Complete file content goes here...
            All lines of the file...
            </content>
        </set_file>
        
        Write the complete content to a file, replacing any existing content.
        The <name> may be a relative or absolute path. Paths are normalized for the current OS.
        Creates the file if it doesn't exist, overwrites if it does. Use this to create and edit files.
        """

    def execute(self, data: Dict[str, Any]) -> str:
        filename = data.get('name')
        content = data.get('content')

        normalized = _normalize_path(str(filename))
        
        # Create directory if it doesn't exist (only if there's a directory part)
        dirname = os.path.dirname(normalized)
        os.makedirs(dirname, exist_ok=True)
        
        with open(normalized, 'w', encoding='utf-8') as f:
            f.write(str(content))
        
        line_count = len(str(content).splitlines()) if content else 0
        print(f"Wrote {normalized} ({line_count} lines)")
        return f"Wrote {normalized} ({line_count} lines)"


class ReadFileTool(Tool):
    dependencies: List[Tool] = []
    stop_token: str = "</read_file>"
    open_files: Dict[str, List[str]] = {}
    stopping: bool = True
    
    def __init__(self, **kwargs):
        super().__init__(stop_token="</read_file>", **kwargs)
        self.open_files = {}

    @property
    def system_description(self) -> str:
        return """
        <read_file>
            <name>filename</name>
        </read_file>
        
        Read a text file into memory (max 5,000 lines per file).
        IMPORTANT: Do not re-read files that are already open. I repeat ONLY READ FILES THAT ARE NOT OPEN.
        """

    @property
    def status_prompt(self) -> str:
        if not self.open_files:
            return ""
        
        sections = []
        for path in self.open_files.keys():
            file_name = os.path.basename(path)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    live_lines = f.readlines()[:5000]
            except (OSError, IOError, FileNotFoundError, PermissionError, UnicodeDecodeError):
                # Fallback to cached content if re-read fails
                live_lines = self.open_files.get(path, [])

            numbered_lines = []
            for i, line in enumerate(live_lines, 1):
                stripped = line[:-1] if line.endswith("\n") else line
                numbered_lines.append(f"{i}. {stripped}")
            content = "\n".join(numbered_lines)
            sections.append(f"File name: {file_name}\n<content>\n{content}\n</content>")
        
        return "\n\n".join(sections)

    def execute(self, data: Dict[str, Any]) -> str:
        filename = data.get('name')
        
        if not filename:
            raise ValueError("filename is required")
        
        normalized = _normalize_path(str(filename))

        # Check if file is already open (use normalized path as key)
        if normalized in self.open_files:
            return f"File {normalized} is already open. Use the content from memory instead of re-reading."
        
        with open(normalized, 'r', encoding='utf-8') as f:
            lines = f.readlines()[:5000]
        
        # Handle empty files
        if not lines:
            self.open_files[normalized] = []
            return f"File {normalized} is empty."
        
        self.open_files[normalized] = lines
        self._enforce_line_limit()
        
        return f"Read {normalized} ({len(lines)} lines)"
    
    def _enforce_line_limit(self):
        total_lines = sum(len(content) for content in self.open_files.values())
        
        while total_lines > 10000 and len(self.open_files) > 1:
            oldest_file = next(iter(self.open_files))
            del self.open_files[oldest_file]
            total_lines = sum(len(content) for content in self.open_files.values())


def _normalize_path(name: str) -> str:
    """Normalize user-provided file paths across OSes and make them absolute.

    - Expands '~'
    - Resolves relative paths against current working directory
    - On macOS, maps '/home/<user>/...' to '/Users/<user>/...' if needed
    - If an absolute path does not exist, attempts to re-root to the current
      working directory by preserving the tail (path under the user directory)
      when possible.
    """
    p = os.path.expanduser(name)

    # Fast path: relative -> absolute
    if not os.path.isabs(p):
        return os.path.realpath(os.path.join(os.getcwd(), p))

    # If it exists, return canonical
    if os.path.exists(p):
        return os.path.realpath(p)

    # macOS: remap /home/<user>/... -> /Users/<user>/...
    if platform.system() == 'Darwin' and p.startswith('/home/'):
        candidate = '/Users/' + p[len('/home/'):]
        if os.path.exists(candidate):
            return os.path.realpath(candidate)

    # Try to preserve tail after the user directory and re-root to CWD
    # Matches both /home/<user>/... and /Users/<user>/...
    m = re.match(r'^/(?:home|Users)/[^/]+/(.+)$', p)
    if m:
        tail = m.group(1)
        candidate = os.path.realpath(os.path.join(os.getcwd(), tail))
        if os.path.exists(candidate):
            return candidate

    # As a last resort, return the absolute path (will likely error later)
    return p
