export interface Shipment {
  /** Parcel weight in grams; a positive integer. */
  weightGrams: number;
  /** ISO 3166-1 alpha-2 destination country, e.g. "NL". */
  destination: string;
  express: boolean;
}

export function assertShipment(shipment: Shipment): void {
  if (!Number.isInteger(shipment.weightGrams) || shipment.weightGrams <= 0) {
    throw new RangeError(`weight must be a positive whole number of grams, got ${shipment.weightGrams}`);
  }
}

/** Carriers bill per started kilogram. */
export function startedKg(shipment: Shipment): number {
  return Math.ceil(shipment.weightGrams / 1000);
}
