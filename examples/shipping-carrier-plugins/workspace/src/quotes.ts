import { UnknownCarrierError, UnsupportedShipmentError } from "./errors";
import { assertShipment, type Shipment, startedKg } from "./shipment";

const CARRIERS = ["postnl", "dhl", "ups"];
const POSTNL_COUNTRIES = ["NL", "BE", "DE", "FR"];

function supports(carrier: string, shipment: Shipment): boolean {
  switch (carrier) {
    case "postnl":
      return POSTNL_COUNTRIES.includes(shipment.destination) && shipment.weightGrams <= 10_000 && !shipment.express;
    case "dhl":
      return shipment.weightGrams <= 30_000;
    case "ups":
      return shipment.weightGrams <= 20_000;
    default:
      throw new UnknownCarrierError(carrier);
  }
}

function price(carrier: string, shipment: Shipment): number {
  const kg = startedKg(shipment);
  switch (carrier) {
    case "postnl":
      return 695 + 100 * Math.max(0, kg - 2);
    case "dhl": {
      const base = 1200 + 150 * kg;
      return shipment.express ? Math.round(base * 1.5) : base;
    }
    case "ups":
      return 990 + (shipment.destination === "NL" ? 0 : 500) + 120 * kg + (shipment.express ? 1500 : 0);
    default:
      throw new UnknownCarrierError(carrier);
  }
}

/** Price in cents for one carrier. */
export function quote(shipment: Shipment, carrier: string): number {
  assertShipment(shipment);
  if (!supports(carrier, shipment)) throw new UnsupportedShipmentError(carrier);
  return price(carrier, shipment);
}

/** Carriers that can ship the parcel, cheapest first; ties by carrier id. */
export function availableCarriers(shipment: Shipment): string[] {
  assertShipment(shipment);
  return CARRIERS.filter((carrier) => supports(carrier, shipment))
    .map((carrier) => ({ carrier, cents: price(carrier, shipment) }))
    .sort((a, b) => a.cents - b.cents || (a.carrier < b.carrier ? -1 : a.carrier > b.carrier ? 1 : 0))
    .map(({ carrier }) => carrier);
}
