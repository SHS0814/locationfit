export interface RequestToken {
  generation: number
  contextGeneration: number
  contextKey: string
}

export class LatestRequestGuard {
  private generation = 0
  private contextGeneration = 0
  private contextKey = ''

  begin(contextKey: string): RequestToken {
    this.activate(contextKey)
    this.generation += 1
    return { generation: this.generation, contextGeneration: this.contextGeneration, contextKey }
  }

  activate(contextKey: string): boolean {
    if (contextKey === this.contextKey) return false
    this.contextKey = contextKey
    this.contextGeneration += 1
    return true
  }

  invalidate(): void {
    this.generation += 1
  }

  isCurrent(token: RequestToken): boolean {
    return this.isLatest(token)
      && token.contextGeneration === this.contextGeneration
      && token.contextKey === this.contextKey
  }

  isLatest(token: RequestToken): boolean {
    return token.generation === this.generation
  }
}
