let archivePromise;
export function loadCases() {
  if (!archivePromise) archivePromise = fetch(`${import.meta.env.BASE_URL}data/cases.json`).then(response => {
    if (!response.ok) throw new Error('사고 사례 데이터를 불러오지 못했습니다.');
    return response.json();
  }).catch(error => { archivePromise = undefined; throw error; });
  return archivePromise;
}
export function filterCases(records, { query = '', group = '', category = '', task = '' }) {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return records.filter(record => (!group || record.group === group) && (!category || record.category === category) && (!task || record.task === task) && terms.every(term => Object.values(record.fields).join(' ').toLocaleLowerCase().includes(term)));
}
