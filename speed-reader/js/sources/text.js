export async function extract(file) {
  const text = await file.text();
  return { title: file.name || '', text };
}
