#!/usr/bin/env python
import GuiTextArea, RouterPacket, F
from copy import deepcopy

class RouterNode():
    myID = None
    myGUI = None
    sim = None
    
    linkcosts = None    
    ncosts = None       
    neighbours = None   
    mincost = None      
    path = None         

    

    # --------------------------------------------------
    def __init__(self, ID, sim, costs):
        self.myID = ID
        self.sim = sim
        self.myGUI = GuiTextArea.GuiTextArea("  Output window for Router #" + str(ID) + "  ")

        self.neighbours = [i for i in range(len(costs)) if costs[i] != sim.INFINITY and costs[i] != 0]
        self.linkcosts = {}
        self.ncosts = {}
        for n in self.neighbours:
            self.ncosts[n] = [self.sim.INFINITY] * self.sim.NUM_NODES
            self.linkcosts[n] = costs[n]

        self.mincost = [i for i in costs]
        self.path = [-1] * self.sim.NUM_NODES

        self.propagate()


    # --------------------------------------------------
    def recvUpdate(self, pkt):
      
        self.ncosts[pkt.sourceid] = pkt.mincost
        changed = self.calcMincost()

     
        if changed:
            self.propagate()

    def calcMincost(self):
        changed = False

        for i in range(self.sim.NUM_NODES):
            
            if i == self.myID:
                self.mincost[i] = 0
            else:
                if i in self.neighbours:
                    
                    new_cost = self.linkcosts[i]
                    path = i
                else:
                   
                    new_cost = self.sim.INFINITY
                    path = -1
                for n in self.neighbours:
                    cost = self.linkcosts[n] + self.ncosts[n][i]
                    if cost < new_cost:
                        new_cost = cost
                        path = n

                if self.mincost[i] != new_cost or self.path[i] == -1:
                    self.mincost[i] = new_cost
                    self.path[i] = path
                    changed = True

        return changed

    # --------------------------------------------------
    def propagate(self):
        

        for n in self.neighbours:
            costs = deepcopy(self.mincost)
          
            if self.sim.POISONREVERSE:
                for i, next in enumerate(self.path):
                    if n == next:
                        costs[i] = self.sim.INFINITY
            pkt = RouterPacket.RouterPacket(self.myID, n, costs)
            self.sendUpdate(pkt)


    # --------------------------------------------------
    def sendUpdate(self, pkt):
        self.sim.toLayer2(pkt)


    # --------------------------------------------------
    def printDistanceTable(self):
        self.myGUI.println("Current table for " + str(self.myID) +
                           "  at time " + str(self.sim.getClocktime()))
        self.myGUI.println("Router\t\tCost\t\tVia")
        for i, cost in enumerate(self.mincost):
            self.myGUI.println(str(i) + "\t\t" + str(cost) + "\t\t" + str(self.path[i]))
        self.myGUI.println("Neighbour\t\tLink Cost\t\tTable")
        for n in self.neighbours:
            self.myGUI.println(str(n) + "\t\t" + str(self.linkcosts[n]) + "\t\t" + str(self.ncosts[n]))
        self.myGUI.println()


    # --------------------------------------------------
    def updateLinkCost(self, dest, newcost):
        self.linkcosts[dest] = newcost
        changed = self.calcMincost()
        if changed:
            self.propagate()
