class Countdown:
    def __init__(self, start: int) -> None:
        self.current = start

    def __iter__(self):      # 返回什么？
        return self

    def __next__(self):      # 什么时候 raise StopIteration？
        if(self.current < 1):
            raise StopIteration
        value = self.current
        self.current -= 1
        return value

if __name__ == "__main__":
    print(list(Countdown(3)))
    c = Countdown(3)
    print([x for x in c])
    print([x for x in c])
