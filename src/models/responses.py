from typing import Dict, List, Optional, Any
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


class HttpFactoryInfoResponse(BaseModel):
    cached_clients: int
    config: Dict[str, float]


class RootResponse(BaseModel):
    name: str
    version: str
    description: str


class ErrorResponse(BaseModel):
    error: str
    details: Optional[str] = None


class ProxyResponse(BaseModel):
    currentUrl: str
    cookie: List[str]
    headers: Dict[str, Any]
    status: int
    body: str
    error: Optional[str] = None


class VideoStreamResponse(BaseModel):
    url: str
    content_type: str
    content_length: int
    supports_range: bool


class ContentInfoResponse(BaseModel):
    status_code: int
    content_type: str
    content_length: int
    accept_ranges: str
    headers: Dict[str, str]
    method_used: str
    error: Optional[str] = None


class ProxyStatsResponse(BaseModel):
    total_working: int
    proxy_stats: Dict[str, Dict[str, int]]
    total_success: int = 0
    total_failures: int = 0


class VideoDetectionResponse(BaseModel):
    is_video: bool
    content_type: str
    content_length: int
    url_pattern_match: bool
    content_type_match: bool


class EncodedRequestParams(BaseModel):
    url: str
    method: str = 'GET'
    headers: Dict[str, str] = {}
    data: Any = None


class RangeHeaderResponse(BaseModel):
    start_byte: int
    end_byte: int
    file_size: int
    content_length: int


class StreamProgressResponse(BaseModel):
    bytes_streamed: int
    total_bytes: int
    percentage: float


class URLInfoResponse(BaseModel):
    url: str
    normalized_url: str
    hostname: str
    scheme: str
    is_valid: bool


class ApiResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    message: Optional[str] = None

class ApiInfoResponse(BaseModel):
    status: str
    timestamp: str
    config: Dict[str, Any]
    http_client_factory: Dict[str, Any]
