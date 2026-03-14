import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { IsInt, IsOptional, ValidateNested } from 'class-validator';

/**
 * Binary tree node DTO.
 *
 * Default value=0 mirrors Jackson Kotlin module behavior:
 * {} deserialises to TreeNode(value=0, left=null, right=null).
 *
 * @ValidateNested + @Type enable recursive deserialization and validation
 * via class-transformer/class-validator.
 */
export class TreeNodeDto {
  @ApiProperty({ default: 0 })
  @IsInt()
  @IsOptional()
  value: number = 0;

  @ApiProperty({ type: () => TreeNodeDto, required: false })
  @IsOptional()
  @ValidateNested()
  @Type(() => TreeNodeDto)
  left?: TreeNodeDto;

  @ApiProperty({ type: () => TreeNodeDto, required: false })
  @IsOptional()
  @ValidateNested()
  @Type(() => TreeNodeDto)
  right?: TreeNodeDto;
}
