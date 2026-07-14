from fastapi.testclient import TestClient
from opportunityos.api.main import app
client=TestClient(app)
def test_health():
    r=client.get('/health');assert r.status_code==200;assert r.json()['status']=='ok'
def test_analysis_endpoint():
    payload={'profile':{'display_name':'Test User','headline':'Fractional Data and AI lead','capabilities':[{'name':'product analytics','proficiency':.9},{'name':'retention','proficiency':.9},{'name':'ai','proficiency':.8}],'preferences':[{'key':'fractional','weight':.95},{'key':'remote','weight':.9}],'constraints':[],'aspirations':[{'name':'data ai leadership','weight':.9}]},'opportunity':{'raw_text':'Company: Acme Consumer\nRole: Fractional Data and AI Lead\nLocation: Remote\nNeed product analytics, retention and AI support.'}}
    r=client.post('/v1/analyses',json=payload);assert r.status_code==200,r.text;body=r.json();assert body['opportunity']['company_name']=='Acme Consumer';assert body['recommendation']['decision'] in {'pursue','hold','reject'}
