export function knowledgeBaseLabel(
  knowledgeBaseId: number,
  namesById: Record<number, string>,
): string {
  const value = namesById[knowledgeBaseId]?.trim()
  return value || `#${knowledgeBaseId}`
}
