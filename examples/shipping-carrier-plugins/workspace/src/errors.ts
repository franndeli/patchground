export class UnknownCarrierError extends Error {
  constructor(readonly carrier: string) {
    super(`unknown carrier: ${carrier}`);
    this.name = "UnknownCarrierError";
  }
}

export class UnsupportedShipmentError extends Error {
  constructor(readonly carrier: string) {
    super(`${carrier} cannot ship this parcel`);
    this.name = "UnsupportedShipmentError";
  }
}
