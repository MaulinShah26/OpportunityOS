from __future__ import annotations
import ipaddress,socket
from html.parser import HTMLParser
from urllib.parse import urlparse
import httpx
from opportunityos.domain.enums import EvidenceType
from opportunityos.domain.models import EvidenceClaim,OpportunityInput
class _VisibleTextParser(HTMLParser):
    def __init__(self):super().__init__();self._skip=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','noscript','svg'}:self._skip+=1
    def handle_endtag(self,tag):
        if tag in {'script','style','noscript','svg'} and self._skip:self._skip-=1
    def handle_data(self,data):
        if not self._skip and data.strip():self.parts.append(data.strip())
def _assert_public_url(url:str)->None:
    parsed=urlparse(url)
    if parsed.scheme not in {'http','https'} or not parsed.hostname:raise ValueError('Only public HTTP(S) URLs are supported')
    try:addresses=socket.getaddrinfo(parsed.hostname,None)
    except socket.gaierror as exc:raise ValueError('Source hostname could not be resolved') from exc
    for address in addresses:
        if not ipaddress.ip_address(address[4][0]).is_global:raise ValueError('Private, loopback, link-local, and reserved addresses are blocked')
class PublicSourceResearchProvider:
    def __init__(self,timeout_seconds:float=15.0,max_source_bytes:int=1000000):self.timeout_seconds=timeout_seconds;self.max_source_bytes=max_source_bytes
    def collect(self,source:OpportunityInput)->list[EvidenceClaim]:
        claims=[]
        if source.raw_text and source.raw_text.strip():claims.append(EvidenceClaim(claim='User-provided opportunity content',claim_type=EvidenceType.OBSERVED_FACT,supporting_excerpt=' '.join(source.raw_text.split())[:5000],confidence=.95))
        if source.source_url:
            url=str(source.source_url);_assert_public_url(url)
            with httpx.Client(timeout=self.timeout_seconds,follow_redirects=True) as client:
                with client.stream('GET',url,headers={'User-Agent':'OpportunityOS/0.1'}) as response:
                    response.raise_for_status();data=bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data)>self.max_source_bytes:raise ValueError('Source exceeded configured size limit')
            parser=_VisibleTextParser();parser.feed(data.decode(response.encoding or 'utf-8',errors='replace'));excerpt=' '.join(parser.parts)[:5000]
            claims.append(EvidenceClaim(claim='Content retrieved from the supplied public URL',claim_type=EvidenceType.OBSERVED_FACT,source_url=source.source_url,supporting_excerpt=excerpt or 'Page contained no extractable visible text.',confidence=.85 if excerpt else .3))
        return claims
class InputOnlyResearchProvider(PublicSourceResearchProvider):
    def collect(self,source:OpportunityInput)->list[EvidenceClaim]:
        if not source.raw_text:return [EvidenceClaim(claim='URL supplied but not fetched in mock mode',claim_type=EvidenceType.OBSERVED_FACT,source_url=source.source_url,supporting_excerpt=str(source.source_url),confidence=.35)]
        return super().collect(OpportunityInput(raw_text=source.raw_text,company_hint=source.company_hint))
