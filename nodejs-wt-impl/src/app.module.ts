import {
  MiddlewareConsumer,
  Module,
  NestModule,
  RequestMethod,
} from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { RequireBodyMiddleware } from './infrastructure/require-body.middleware';
import { TreesModule } from './trees/trees.module';

@Module({
  imports: [ConfigModule.forRoot({ isGlobal: true }), TreesModule],
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer): void {
    consumer
      .apply(RequireBodyMiddleware)
      .forRoutes({ path: 'api/v1/trees/level-order', method: RequestMethod.POST });
  }
}
