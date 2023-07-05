import time
# from multiprocessing import Queue as multiQueue
# from multiprocessing import Process
# from multiprocessing import Queue as JoinableQueue
# from multiprocessing import Lock
from threading import Thread
import threading
from queue import Queue

class frame:
    def __init__(self, name, sender, receiver, priority=7, size=100,frequency=10,lis_SFC=[]):
        # 例： sensor_pressure2 = frame("sensor_pressure", "machine2", "controler2", 5, 100, 100, [se1, se5])  # size的单位是bit
        self.name = name
        self.size = size
        self.frequency=frequency
        self.priority = priority
        self.timestamp = time.time()
        self.time = 0        #最后，记录下总的传输时间
        self.sender = sender
        self.receiver = receiver
        self.lis_SFC = lis_SFC
        self.path = []
        self.current_node=0    # path列表中的指示器

class VNF:#待完成，里面有VNF的种类以及处理速度信息
    def __init__(self,id,name,speed):
        super(VNF, self).__init__()
        self.id=id
        self.name=name
        self.speed=speed#单位Mbps

# 将TSN数控系统中的每一个组件，如video、controler、switch等，抽象为一个类
class Object(Thread):
    def __init__(self, name, lst_message, bw, queue_in, queue_out,dic_vnf_q):
        super(Object, self).__init__()
        self.name=name
        self.lst_message = lst_message        # 是list, 内装 dict  定义设备所produce的数据：frame及 间隔
        self.bw = bw                  # 如 {"in": 0.1, "out": 0.1}  单位是多少？
        self.queue_in = queue_in      # 如果设备需从多个源读数据呢：按端口分类？  如果设备从多个端口读数据呢？
        self.queue_out = queue_out    # 如果设备 要产生多个端口的数据，怎么办？
        self.queue_wait = Queue()     #自带的缓冲区
        self.dic_vnf_q=dic_vnf_q

    def run(self):
        if(self.queue_in):                        # 指定了读入队列时，才启动读
            Thread(target=self.read,name=self.name+"_read").start()     # 读启动

        for msg in self.lst_message:           #不同的message类型，启动不同的produce  注意！！，这些不同类型的message是混杂发送的
            Thread(target=self.produce,args=(msg,),name=self.name+"_produce_msg").start()

        if(self.queue_out):
            Thread(target=self.output,name=self.name+"_output").start()  # 输出启动


    def read(self):
        while 1:
            msg = self.queue_in.get()  # 如果没有数据会阻塞
            msg.current_node+=1        ###########  路径path指示加1
            time.sleep(msg.size * 1000 / (self.bw["in"] * pow(1024, 3)))  # 读数据的时延,单位为ms，但是放大了1000倍
            transportation_time = time.time() - msg.timestamp
            msg.time = transportation_time
            print("  %s read: 数据包 %s，传输时间为%s ms" % (self.name, msg.name, transportation_time))
            print("           数据包%s的路径是%s，指针是%s" % (msg.name,msg.path,msg.current_node))

    def output(self):
        while 1:
            msg = self.queue_wait.get()
            print("  %s output: 数据包 %s" % (self.name, msg.name,))
            time.sleep(msg.size * 1000 / (self.bw["out"] * pow(1024, 3)))
            self.queue_out.put(msg)

    def produce(self, msg):             # dict_msg是 frame
        """
        按{message}产生规定的frame, 并放网上
        """
        i = 0
        #for j in range(1):
        while(1):
            #根据VNF序列决定path路径表，选取最短路径
            #node_ind = 0
            msg.path.clear()
            msg.path.append(self.name)
            for se in msg.lis_SFC:                    # msg.lis_SFC 举例：[se1, se3, se6]
                # 初始化，len取int的最大值
                len = 10000                           ############ 够大么？
                short_server = ""
                for server_now in self.dic_vnf_q[se.name].keys():    # dir_vnf_q 由se找到server及其queue 的dict
                    #打印每种vnf的每个队列中排队数
                    #print("vnf %s, server %s, queue size %s" % (se.id, server_now, dir_vnf_q[se][server_now].qsize()))
                    if (len > self.dic_vnf_q[se.name][server_now].qsize()):
                        len = self.dic_vnf_q[se.name][server_now].qsize()
                        short_server = server_now
                #node_ind += 1
                msg.path.append(short_server)        #######每个frame在产生时就 决定了 se server的路径 ???????
                #打印出选择的服务器
                #print("vnf %s, choose server %s" % (se.id, short_server))
            msg.path.append(msg.receiver)            ########路径不应在开始固定，且数据无需总是在server与switch之间移动，也可能是直接在server上连续处理

            #产生数据流
            name = self.name + ":" + msg.name + "-" + str(i)
            frame_produce = frame(name, self.name, msg.receiver, msg.priority,
                                  msg.size, msg.frequency, msg.lis_SFC)######如果设备固定SFC，则在这里进行处理，这里还能插入路径选择1算法
            print("  %s produce: 数据包 %s" % (self.name, name,))
            i = i + 1
            frame_produce.path=msg.path.copy()             ################# 两个path是同一个对象：可能不行： path是乱的

            self.queue_wait.put(frame_produce)
            time.sleep(msg.frequency)  # 读数据的时延


# 一个带时钟的switch：switch启动时，时钟启动
# 在输入端：交换机持续读取输入数据，处理后，按数据敏感，把数据分别放入缓冲区：敏感队列1与非敏感队列2
# 在输出端：交换机按状态时间窗口，分别输出敏感数据与普通数据
# 问题：交换机的缓冲区有无大小限制
class Switch(Thread):
    def __init__(self, name, bw, l_phy, in_q, out_q):
        super(Switch, self).__init__()
        self.name = name
        self.bw = bw
        self.l_phy = l_phy
        self.in_q = in_q  # 输入队列
        self.out_q = out_q  # 输出队列
        self.status = 0  # 交换机的初始门控状态为0
        self.temp_hi_q = Queue()  # 交换机的内部缓冲区1
        self.temp_normal_q = Queue()  # 交换机的内部缓冲区2

    def run(self):
        Thread(target=self.tick).start()  # 时钟启动
        Thread(target=self.read).start()  # 读启动
        Thread(target=self.output_tick0).start()  # 输出窗口0启动
        Thread(target=self.output_tick1).start()  # 输出窗口1启动
        Thread(target=self.output_tick2).start()  # 输出窗口2启动

    def read(self):
        while 1:
            msg = self.in_q.get()
            print("    switch read: 数据包 %s" % (msg.name,))
            time.sleep(msg.size * 1000 / (self.bw["in"] * pow(1024, 3)) + self.l_phy["l_phy1"])  # 处理一个数据的时延
            # time.sleep(self.l_phy["l_phy1"])  # 读数据的时延
            #msg.path = msg.path + self.name  # 记录路径

            if (msg.priority == 7 or msg.priority == 6):        ###### 这里王志通错了
                self.temp_hi_q.put(msg)  # 敏感数据放入缓冲区
            else:
                self.temp_normal_q.put(msg)

    def output_tick0(self):
        while (True):
            if (self.status == 0):
                msg = self.temp_hi_q.get()      # 如果队列没有数据，线程会阻塞
                print("    --switch: 缓冲区输出时间敏感数据 %s:" % msg.name)
                time.sleep(msg.size * 1000 / (self.bw["out"] * pow(1024, 3)) + self.l_phy["l_phy2"])  # 缓存输出所需的延时
                #check_out_queue(msg)#查看msg的接收端与端口的匹配信息
                #if msg.receiver == "mmachine1":
                next_device = msg.path[msg.current_node + 1]          # 修改path列表的指针
                if(next_device in self.out_q.keys()):
                    self.out_q[next_device].put(msg)
                else:
                    print("error: %s not in out_q" % next_device)
                #self.out_q.put(msg)

    def output_tick1(self):
        while (True):
            if (self.status == 1):
                msg = self.temp_normal_q.get()
                print("    --switch: 缓冲区输出普通数据 %s:" % msg.name)
                time.sleep(msg.size * 1000 / (self.bw["out"] * pow(1024, 3)) + self.l_phy["l_phy2"])  # 缓存输出所需的延时
                next_device = msg.path[msg.current_node + 1]
                if (next_device in self.out_q.keys()):
                    self.out_q[next_device].put(msg)
                else:
                    print("error: %s not in out_q" % next_device)
                #self.out_q.put(msg)

    def output_tick2(self):
        while (True):
            if (self.status != 0&self.status != 1):
                # print("  switch: 处于保护带")
                time.sleep(0.01)

    def tick(self):
        while True:
            self.status = 0
            # print("tick: now 时间敏感窗口")
            time.sleep(0.45)
            # print("tick: now 时间不敏感窗口")
            self.status = 1
            time.sleep(0.5)
            self.status = 2
            # print("tick: now 保护带窗口")
            time.sleep(0.05)


class Server(Thread):
    def __init__(self,name,dic_bw,queue_in,queue_out,dic_vnfqueue):#dic_vnfqueue为一个字典，key为vnf，value为一个队列
        #半成品，read操作为将queue_in中的数据读出，然后放入对应的dic_vnfqueue中的队列中
        #process操作为将dic_vnfqueue中的元素取出，处理一定的时间，放入queue_wait中
        #output操作为将queue_wait中的元素取出，放入queue_out中
        super(Server, self).__init__()
        self.name=name
        #self.lis_vnf=lis_vnf
        self.dic_bw=dic_bw
        self.queue_in=queue_in
        self.queue_wait=Queue()
        self.queue_out=queue_out
        self.dic_vnfqueue = dic_vnfqueue

    def run(self):
        Thread(target=self.read).start()
        for vnf in self.dic_vnfqueue.keys():                # 一个VNF对象的queue, 开一个线程
            Thread(target=self.process,args=(vnf,)).start()
        Thread(target=self.output).start()

    def read(self):
        while True:
            msg=self.queue_in.get()
            msg.current_node+=1
            sleep_time=msg.size*1000/(self.dic_bw["in"]*pow(1024,3))
            time.sleep(sleep_time)
            # 根据current_node指定的sfc_chain值放入指定队列   msg.lis_SFC 内容举例：[se1, se3, se6] 由se找到相关server的队列
            self.dic_vnfqueue[msg.lis_SFC[msg.current_node-1]].put(msg)    # se的位置总比path中的位置差一个
            print("    server %s read： msg %s"%(self.name,msg.name))

    def process(self,vnf):
        while True:
            msg=self.dic_vnfqueue[vnf].get()
            sleep_time=msg.size*1000/(vnf.speed*pow(1024,2))             ####是Mbps, 是2次方
            time.sleep(sleep_time)
            self.queue_wait.put(msg)
            # print("    server %s process: msg %s,vnf.id is %s"%(self.name,msg.name,vnf.name))

    def output(self):
        while True:
            msg=self.queue_wait.get()
            sleep_time=msg.size*1000/(self.dic_bw["out"]*pow(1024,3))
            time.sleep(sleep_time)
            self.queue_out.put(msg)                                     ####server的输出不应总是 switch, 也可能是自己
            print("    server %s output: msg %s"%(self.name,msg.name))


#dir_server_q = {}                                                           ##############不要
if __name__ == '__main__':
    dir_vnf_q = {}  # 是一个二维字典，第一位是vnf，VNF类型，第二维是服务器名称，string类型    #############################
    #声名vnf
    se1=VNF(1,"se1",100)
    se2=VNF(2,"se2",200)
    se3=VNF(3,"se3",300)
    se4=VNF(4,"se4",400)
    se5=VNF(5,"se5",50)
    se6=VNF(6,"se6",20)
    se7=VNF(7,"se7",5)
    se8=VNF(8,"se8",1)
    #利用vnf池进一步初始化dir_vnf_q
    vnf_pool=[se1,se2,se3,se4,se5,se6,se7,se8]
    for vnf in vnf_pool:
        dir_vnf_q[vnf.name]={}
    # mechine1的数据流
    sensor_displayment = frame("sensor_displayment", "machine1", "controler1", 6, 100, 3,[se1, se3, se6])  # size的单位是bit
    sensor_acceleration = frame("sensor_acceleration", "machine1", "controler1", 6, 100, 20,[se2, se4, se8])  # size的单位是bit
    sensor_temprature = frame("sensor_temprature", "machine1", "controler1", 5, 100, 100,[se3, se4, se7])  # size的单位是bit
    sensor_pressure = frame("sensor_pressure", "machine1", "controler1", 5, 100, 100, [se2, se8])  # size的单位是bit

    # controler1的数据流
    control_intruction1 = frame("control_intruction2", "controler1", "machine1", 7, 500, 10,[se1, se5, se6])  # size的单位是bit
    control_intruction2 = frame("control_intruction2", "controler1", "machine1", 7, 300, 3,[se3, se5, se8])  # size的单位是bit

    # mathine2的数据流
    sensor_displayment2 = frame("sensor_displayment", "machhine2", "controler2", 6, 100, 2,[se2, se5, se6])  # size的单位是bit
    sensor_acceleration2 = frame("sensor_acceleration", "machhine2", "controler2", 6, 100, 10,[se2, se6, se7])  # size的单位是bit
    sensor_temprature2 = frame("sensor_temprature", "machine2", "controler2", 5, 100, 100,[se4, se5, se8])  # size的单位是bit
    sensor_pressure2 = frame("sensor_pressure", "machine2", "controler2", 5, 100, 100, [se1, se5])  # size的单位是bit

    # controler2的数据流
    control_intruction3 = frame("control_intruction2", "controler2", "machine2", 7, 1000, 5, [se1, se8])  # size的单位是bit
    control_intruction4 = frame("control_intruction2", "controler2", "machine2", 7, 700, 2, [se2, se8])  # size的单位是bit

    # 交换机输入队列
    switch1_in = Queue()
    # 流表
    switch1_out={}

    #数据集用字典对应
    dic_message={"machine1":[sensor_displayment, sensor_acceleration, sensor_temprature, sensor_pressure],      #这样看得舒服
                 "controler1":[control_intruction1, control_intruction2],
                 "machine2":[sensor_displayment2, sensor_acceleration2, sensor_temprature2, sensor_pressure2],
                 "controler2":[control_intruction3, control_intruction4]}

    #object出入口带宽的字典                                                                                        ##########这个也可以简化
    dir_bw={"machine1":{"in":0.1,"out":0.1},"controler1":{"in":0.1,"out":0.1},"machine2":{"in":0.1,"out":0.1},"controler2":{"in":0.1,"out":0.1}}

    #object池
    object_pool=[]

    #自动循环生成队列与Object对象,并将其输入队列加入switch1_out字典
    for object_name in dic_message.keys():   ############应从 object_pool产生
        # 每个设备对象对应的queue
        locals()[object_name+"_in"]=Queue()
        # 生成每个object对象, 示例： machine1 = Object("machine1", lst_machine1_message, {"in": 0.1, "out": 0.1}, machine1_in,switch1_in)
        locals()[object_name]=Object(object_name,dic_message[object_name],dir_bw[object_name],locals()[object_name+"_in"],switch1_in,dir_vnf_q)#生成Object对象
        # 将Object对象加入 池
        object_pool.append(locals()[object_name])
        # switch1_out示例：switch1_out = {"machine1": machine1_in, "controler1": controler_in, "machine2": machine2_in......}
        switch1_out[object_name]=locals()[object_name+"_in"]
        #print(locals()[object_name].name)

    #组建server和vnf对应的字典
    dir_server={"server1":[se1,se2,se3,se8],"server2":[se4,se5,se6,se7],"server3":[se1,se2,se3,se8],"server4":[se4,se5,se6,se7]}
    dir_server_bw={"server1":{"in":0.1,"out":0.1},"server2":{"in":0.1,"out":0.1},"server3":{"in":0.1,"out":0.1},"server4":{"in":0.1,"out":0.1}}

    #server池
    server_pool=[]
    #根据字典循环生成server_in队列，根据server和vnf对应关系生成dir_server_q二维字典，以及dir_vnf_q二维字典，二维字典装的是queue类型数据，并将其输入队列加入switch1_out字典
    for serverName in dir_server.keys():
        locals()[serverName + "_in"]=Queue()  # 生成server_in队列
        locals()["dir_" + serverName]={}      # 生成dir_server字典，对于每个server，生成一个字典，key是vnf，value是queue  !!!!!!!!!这个不是已经有了么？？？？？？
        for vnf in dir_server[serverName]:  # 循环生成dir_server字典,同时生成dir_vnf_q字典
            # 对每一个服务器上的VNF都生成一个queue
            locals()[serverName + "-" + vnf.name]=Queue()                         ################ 这个好象没有用，可简化
            # 生成类似这样：dir_server1 = {se1: q1_1, se2: q1_2, se3: q1_3, se8: q1_8}
            locals()["dir_" + serverName][vnf]=locals()[serverName + "-" + vnf.name]    #######把 queue放到 dir_server1，dir_server2字典中
            # 生成由 se 查找 server的字典  示例：dir_vnf_q[se1] = {"server1": q1_1}
            dir_vnf_q[vnf.name][serverName]=locals()[serverName + "-" + vnf.name]

        # 生成server对象，最后样子 server1 = Server("server1", {"in": 0.1, "out": 0.1}, server1_in, switch1_in, dir_server1)
        locals()[serverName]=Server(serverName, dir_server_bw[serverName], locals()[serverName + "_in"], switch1_in, locals()["dir_" + serverName])
        # 将所有server对象加入server_pool
        server_pool.append(locals()[serverName])
        # 最后可能样子： switch1_out = {"machine1": machine1_in, "controler1": controler_in, "machine2": machine2_in......}
        switch1_out[serverName]=locals()[serverName + "_in"]  # 将server_in队列加入switch1_out字典
        # 最后结果样子：dir_server_q={"server1":[se1_q,se2_q,se3_q,se8-q],"server2":[se4_q,se5_q,se6_q,se7_q],"server3":[XXX],"server4":[XXX]}
        #dir_server_q[serverName]=locals()["dir_" + serverName]#将dir_server字典加入dir_server_q字典      ##########！！！！！！！！！你这不是改了 循环体

    # 各种交换机的集合
    switch1 = Switch("myswitch", {"in": 0.1, "out": 0.1}, {"l_phy1": 0.01, "l_phy2": 0.01}, switch1_in, switch1_out)

    # 任务启动
    switch1.start()
    for obj in object_pool:
        obj.start()
    for server in server_pool:
        server.start()


####总体思路：
## 所有的se对象（VNF对象）放pool中  (自动生成对应的queue)
## 所有的frame对象 （其中的SFC表放有se对象）

## 所有object的带宽表
## 所有object要产生的frame的对应表
   ## -->所有的object对象放pool中 (自动生成对应的queue)

## server与se对象的对应表  （server.name为键）

## 所有server的带宽表
     #--> 所有的server对象放pool中 （自动生成对应的queue）
     #--> se查找server对象的表 （用se.name作键）

## switch对象单独定义，switch_in单独定义

## 还研究了改 进程
