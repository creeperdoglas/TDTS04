#!/usr/bin/env python
# code by melgu374 and antfo614
import GuiTextArea, RouterPacket, F
from copy import deepcopy
from F import F

class RouterNode():
    def __init__(self, ID, sim, costs):
        self.myID = ID
        self.sim = sim
        self.myGUI = GuiTextArea.GuiTextArea(f"Output window for Router #{ID}")

        self.costs = deepcopy(costs)
        self.neighbors = [i for i in range(len(costs)) if costs[i] != sim.INFINITY and i != ID]
        self.distanceTable = [[sim.INFINITY]*sim.NUM_NODES for _ in range(sim.NUM_NODES)]
        self.distanceVector = deepcopy(costs)
        self.nextHops = [i if costs[i] != sim.INFINITY else None for i in range(sim.NUM_NODES)]

        self.initRouteTable()
        self.propagate()

    def initRouteTable(self):
        for i in range(self.sim.NUM_NODES):
            self.distanceTable[self.myID][i] = self.costs[i]
            if self.costs[i] != self.sim.INFINITY and i != self.myID:
                self.nextHops[i] = i
            else:
                self.nextHops[i] = None

    def recvUpdate(self, pkt):
        source = pkt.sourceid
        updated = False

        # Spara mottagen distansvektor från granne
        for dest in range(self.sim.NUM_NODES):
            self.distanceTable[source][dest] = pkt.mincost[dest]

        # Uppdatera vår egen distansvektor baserat på nya uppgifter
        for dest in range(self.sim.NUM_NODES):
            if dest == self.myID:
                continue

            min_cost = self.costs[dest]
            next_hop = self.nextHops[dest]

            for neighbor in self.neighbors:
                potential_cost = self.costs[neighbor] + self.distanceTable[neighbor][dest]
                if potential_cost < min_cost:
                    min_cost = potential_cost
                    next_hop = neighbor

            if min_cost != self.distanceVector[dest]:
                self.distanceVector[dest] = min_cost
                self.nextHops[dest] = next_hop
                updated = True

        if updated:
            self.propagate()

    def propagate(self):
        for neighbor in self.neighbors:
            sendVector = deepcopy(self.distanceVector)

            if self.sim.POISONREVERSE:
                for i in range(self.sim.NUM_NODES):
                    if self.nextHops[i] == neighbor:
                        sendVector[i] = self.sim.INFINITY

            packet = RouterPacket.RouterPacket(self.myID, neighbor, sendVector)
            self.sim.toLayer2(packet)

    def updateLinkCost(self, dest, newcost):
        self.costs[dest] = newcost
        self.distanceTable[self.myID][dest] = newcost

        updated = False

        for dst in range(self.sim.NUM_NODES):
            if dst == self.myID:
                continue

            min_cost = min(
                self.costs[neighbor] + self.distanceTable[neighbor][dst]
                for neighbor in self.neighbors
            )

            if min_cost != self.distanceVector[dst]:
                self.distanceVector[dst] = min_cost
                self.nextHops[dst] = min(
                    self.neighbors,
                    key=lambda neighbor: self.costs[neighbor] + self.distanceTable[neighbor][dst]
                )
                updated = True

        if updated:
            self.propagate()

    def printDistanceTable(self):
        self.myGUI.println(f"Current state for router {self.myID} at time {self.sim.getClocktime()}")
        self.myGUI.println("\nDistancetable:")
        header = f"    dst |" + "  ".join(f"{i}" for i in range(self.sim.NUM_NODES))
        self.myGUI.println(header)
        self.myGUI.println("-" * len(header))

        for nbr in [self.myID] + self.neighbors:
            row = f"nbr {nbr} | " + "  ".join(F.format(self.distanceTable[nbr][dst], 3) for dst in range(self.sim.NUM_NODES))
            self.myGUI.println(row)

        self.myGUI.println("\nOur distance vector and routes:")
        self.myGUI.println("dst  |  " + "  ".join(f"{i}" for i in range(self.sim.NUM_NODES)))
        self.myGUI.println("-" * len(header))

        costs_row = "cost  |  " + "  ".join(str(self.distanceVector[i]) for i in range(self.sim.NUM_NODES))
        routes_row = "route |  " + "  ".join(str(self.nextHops[i]) if self.nextHops[i] is not None else "-" for i in range(self.sim.NUM_NODES))

        self.myGUI.println(costs_row)
        self.myGUI.println(routes_row)
