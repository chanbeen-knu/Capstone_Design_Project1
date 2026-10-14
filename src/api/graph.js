// Neo4j 지식그래프 API 호출

async function getJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    let detail = `요청 실패 (${response.status})`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
    
    }
    throw new Error(detail);
  }
  return response.json();
}

/** 기인물 목록 [{ name, cases }] (사례 수 많은 순) */
export const fetchObjects = () => getJson('/api/objects');

/** 기인물 중심 그래프 */
export const fetchObjectGraph = (name) =>
  getJson(`/api/graph/object/${encodeURIComponent(name)}`);

/** 사고사례 상세 */
export const fetchCase = (id) => getJson(`/api/cases/${encodeURIComponent(id)}`);
