export type Message = {
  id: string;
  content: string;
  from: 'user' | 'llm'
}