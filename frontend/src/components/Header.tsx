import { Link } from '@tanstack/react-router'
import { Home, Menu, Monitor, ScanSearch } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { Separator } from '@/components/ui/separator'

export default function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 items-center px-4">
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="mr-2">
              <Menu className="size-5" />
              <span className="sr-only">打开菜单</span>
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-72">
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                <ScanSearch className="size-5 text-primary" />
                导航菜单
              </SheetTitle>
            </SheetHeader>
            <Separator className="my-4" />
            <nav className="flex flex-col gap-2">
              <Link to="/">
                {({ isActive }) => (
                  <Button
                    variant={isActive ? 'default' : 'ghost'}
                    className="w-full justify-start gap-3"
                  >
                    <Home className="size-4" />
                    首页
                  </Button>
                )}
              </Link>
              <Link to="/screen">
                {({ isActive }) => (
                  <Button
                    variant={isActive ? 'default' : 'ghost'}
                    className="w-full justify-start gap-3"
                  >
                    <Monitor className="size-4" />
                    手机屏幕
                  </Button>
                )}
              </Link>
            </nav>
          </SheetContent>
        </Sheet>

        <Link to="/" className="flex items-center gap-2">
          <ScanSearch className="size-6 text-primary" />
          <span className="font-semibold text-lg">图片差异检测</span>
        </Link>
      </div>
    </header>
  )
}
