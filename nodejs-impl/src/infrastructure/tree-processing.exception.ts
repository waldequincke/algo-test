export class TreeProcessingException extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'TreeProcessingException';
  }
}
