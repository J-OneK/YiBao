"""
数据模型定义
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ImageInfo:
    """图片信息类"""
    image_id: str
    image_url: str
    att_type_code: int
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class ExtractedField:
    """提取的字段信息"""
    key_desc: str
    value: str
    pixel: List[int]  # [a, b, c, d] - 归一化坐标 [0-999]
    image_id: Optional[str] = None
    att_type_code: Optional[int] = None


@dataclass
class ExtractionResult:
    """单张图片的识别结果"""
    pre_dec_head: List[ExtractedField] = field(default_factory=list)
    pre_dec_list: List[List[ExtractedField]] = field(default_factory=list)
    image_id: Optional[str] = None


@dataclass
class SourceItem:
    """来源信息"""
    value: str
    startx: int
    starty: int
    endx: int
    endy: int
    image_id: str


@dataclass
class AggregatedField:
    """聚合后的字段"""
    key_desc: str
    key: str
    parsed_value: str
    source_list: List[SourceItem] = field(default_factory=list)


@dataclass
class FinalResult:
    """最终输出结果"""
    pre_dec_head: List[AggregatedField] = field(default_factory=list)
    pre_dec_list: List[List[AggregatedField]] = field(default_factory=list)

